// strata/platform/robust_read.hpp - positional reads that survive a slow or remote file system.
//
// A model on a network store (an S3-backed FUSE mount, NFS) can refuse a read for a moment where a local SSD never
// does: ENOMEM from the mount's own buffer limit when many readers are open at once, EIO or a time-out from the
// link.  `read_at` retries those with a growing pause, and through a shared `ReadGate` halves how many readers run
// at once each time one of them is refused.  `read_range` loads one contiguous range with several readers, each
// on a handle of its own, because such a store's speed is per stream.
#pragma once

#if !defined(_WIN32)

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <unistd.h>

namespace strata::platform {

/// `pread`'s signature; the tests pass a function that fails on purpose.
using PreadFn = ssize_t (*)(int, void*, size_t, off_t);

/// How many readers may be inside a read at once.  It starts at the reader count, is halved when the store refuses
/// a read, and climbs back by one after every `kRecover` reads in a row that worked.
class ReadGate {
public:
    explicit ReadGate(int readers) : limit_(std::max(readers, 1)), most_(limit_) {}

    /// Waits for a place and returns the limit in force at that moment (what `refused` wants back).
    int enter() {
        std::unique_lock<std::mutex> lk(mu_);
        cv_.wait(lk, [&] { return active_ < limit_; });
        ++active_;
        return limit_;
    }
    /// `ok`: the read returned bytes.
    void leave(bool ok = true) {
        {
            std::lock_guard<std::mutex> lk(mu_);
            --active_;
            if (!ok) good_ = 0;
            else if (limit_ < most_ && ++good_ >= kRecover) {
                ++limit_;
                good_ = 0;
            }
        }
        cv_.notify_all();
    }
    /// A read that entered under `seen` was refused.  Halves the limit once per burst: readers refused together
    /// all saw the same limit, and only the first of them lowers it.  Returns the new limit, 0 if unchanged.
    int refused(int seen) {
        std::lock_guard<std::mutex> lk(mu_);
        if (seen != limit_ || limit_ == 1) return 0;
        limit_ = std::max(limit_ / 2, 1);
        good_ = 0;
        return limit_;
    }
    int limit() {
        std::lock_guard<std::mutex> lk(mu_);
        return limit_;
    }

private:
    std::mutex mu_;
    std::condition_variable cv_;
    static constexpr int kRecover = 32;
    int limit_;
    int most_;
    int active_ = 0;
    int good_ = 0;
};

/// The errors a remote store gives for a read that works when asked again.
inline bool read_error_is_transient(int e) {
    switch (e) {
        case ENOMEM: case EAGAIN: case EIO: case ETIMEDOUT: case ENOBUFS: case EBUSY: case ESTALE:
        case ECONNRESET: case ECONNABORTED: case ENETDOWN: case ENETUNREACH: case EHOSTUNREACH: case ENOTCONN:
            return true;
        default:
            return false;
    }
}

inline std::string read_error(const std::string& path, uint64_t off, int e) {
    return "cannot read " + path + " at offset " + std::to_string(off) + ": " +
           (e == ENODATA ? std::string("the file ends before that") : std::string(std::strerror(e)));
}

/// Reads exactly `n` bytes at `off`.  Returns 0, or the errno of the read that could not be completed: ENODATA if
/// the file ends early, a transient error only after `max_wait_s` seconds of retries without one byte arriving.
inline int read_at(int fd, void* buf, size_t n, uint64_t off, ReadGate& gate, PreadFn pread_fn = ::pread,
                   double max_wait_s = 120.0) {
    size_t done = 0;
    double pause = 0.05, waited = 0.0;
    while (done < n) {
        const int seen = gate.enter();
        const ssize_t got = pread_fn(fd, (uint8_t*) buf + done, n - done, (off_t) (off + done));
        const int e = got < 0 ? errno : 0;
        gate.leave(got > 0);
        if (got > 0) {
            done += (size_t) got;
            pause = 0.05;
            waited = 0.0;
            continue;
        }
        if (got == 0) return ENODATA;
        if (e == EINTR) continue;
        if (!read_error_is_transient(e) || waited >= max_wait_s) return e;
        const int now = gate.refused(seen);
        if (now > 0)
            std::fprintf(stderr, "strata: a read was refused (%s); retrying with at most %d reader%s at once for now\n",
                         std::strerror(e), now, now == 1 ? "" : "s");
        std::this_thread::sleep_for(std::chrono::duration<double>(pause));
        waited += pause;
        pause = std::min(pause * 2.0, 5.0);
    }
    return 0;
}

/// Loads `bytes` at `off` of `path` into `dst` with up to `readers` readers.  With `what`, progress goes to stderr
/// every 4 GiB.  False with `err` set on failure.
inline bool read_range(const std::string& path, uint64_t off, uint8_t* dst, uint64_t bytes, int readers,
                       std::string& err, const char* what = nullptr, PreadFn pread_fn = ::pread,
                       double max_wait_s = 120.0) {
    constexpr uint64_t kChunk = 16ull << 20;
    const uint64_t n_chunks = (bytes + kChunk - 1) / kChunk;
    readers = (int) std::clamp<uint64_t>((uint64_t) std::max(readers, 1), 1, std::max<uint64_t>(n_chunks, 1));
    ReadGate gate(readers);
    std::atomic<uint64_t> next{0}, loaded{0};
    std::atomic<bool> bad{false};
    std::mutex err_mu;
    const auto t0 = std::chrono::steady_clock::now();
    auto fail = [&](const std::string& m) {
        std::lock_guard<std::mutex> lk(err_mu);
        if (!bad.exchange(true)) err = m;
    };
    auto worker = [&]() {
        const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
        if (fd < 0) {
            fail("cannot open " + path + ": " + std::strerror(errno));
            return;
        }
        for (;;) {
            const uint64_t c = next.fetch_add(1);
            if (c >= n_chunks || bad) break;
            const uint64_t at = c * kChunk, n = std::min(kChunk, bytes - at);
            const int e = read_at(fd, dst + at, (size_t) n, off + at, gate, pread_fn, max_wait_s);
            if (e != 0) {
                fail(read_error(path, off + at, e));
                break;
            }
            const uint64_t was = loaded.fetch_add(n);
            if (what != nullptr && (was + n) >> 32 != was >> 32) {
                const double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
                std::fprintf(stderr, "strata: %s: %.0f of %.1f GiB read (%.0f MB/s)\n", what,
                             (double) (was + n) / 1073741824.0, (double) bytes / 1073741824.0,
                             s > 0 ? (double) (was + n) / 1e6 / s : 0.0);
            }
        }
        ::close(fd);
    };
    std::vector<std::thread> pool;
    for (int i = 1; i < readers; ++i) pool.emplace_back(worker);
    worker();
    for (auto& t : pool) t.join();
    return !bad;
}

}  // namespace strata::platform

#endif  // !_WIN32
