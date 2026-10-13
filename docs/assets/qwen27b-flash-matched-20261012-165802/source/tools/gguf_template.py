"""Read GGUF metadata without dependencies or loading tensors."""
import struct

def metadata(path):
    with open(path,'rb') as f:
        def unpack(fmt):return struct.unpack('<'+fmt,f.read(struct.calcsize('<'+fmt)))[0]
        def string():return f.read(unpack('Q')).decode()
        def value(kind):
            if kind==8:return string()
            if kind==9:
                typ,n=unpack('I'),unpack('Q')
                return [value(typ) for _ in range(n)]
            return unpack({0:'B',1:'b',2:'H',3:'h',4:'I',5:'i',6:'f',7:'?',10:'Q',11:'q',12:'d'}[kind])
        assert f.read(4)==b'GGUF';version=unpack('I');assert version in (2,3)
        tensors,count=unpack('Q'),unpack('Q');out={}
        for _ in range(count):
            key=string();v=value(unpack('I'))
            if key in ('tokenizer.chat_template','general.name','general.architecture','general.file_type'):out[key]=v
        return out
if __name__=='__main__':
    import json,sys
    print(json.dumps(metadata(sys.argv[1]),indent=2))
