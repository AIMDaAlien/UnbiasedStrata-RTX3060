"""Checks for controls that otherwise silently invalidate A/B experiments."""
import unittest
from unittest.mock import patch
from launch import optimization_environment, command
from paired_report import evaluate, BUCKETS

class Controls(unittest.TestCase):
    def test_forward_override_unset_and_no_secrets(self):
        with patch.dict('os.environ', {'STRATA_PF_FUSED':'0','STRATA_PREFILL_TIMING':'1','SECRET':'private'},clear=True):
            e=optimization_environment({'environment':{'STRATA_PF_FUSED':'1','STRATA_PREFILL_TIMING':None,'STRATA_PF_FUSED_TILE':64}})
            self.assertEqual(e['STRATA_PF_FUSED'],'1')
            self.assertEqual(e['STRATA_PF_FUSED_TILE'],'64')
            self.assertNotIn('SECRET',e)
            self.assertNotIn('STRATA_PREFILL_TIMING',e)
    def test_reject_arbitrary_environment(self):
        with self.assertRaises(ValueError): optimization_environment({'environment':{'LD_PRELOAD':'bad'}})
    def test_kv_constraint(self):
        with self.assertRaises(ValueError): command({'kv':'q4_0','kv_resident':32768})
    def test_amd_decode_flag(self):
        p=dict(model='m',pack='p',mtp='d',port=1,context=196608,threads=12,ple_io='direct',spec=4,
               amd_helper='worker',amd_device='GPU-test',amd_decode_only=True)
        self.assertIn('--amd-decode-only',command(p))

class Gates(unittest.TestCase):
    def record(self, ratio=1):
        return {'status':'passed','profile':dict(context=196608,kv='int8',model='m',mtp='d'),
                'runs':[dict(workload=w,target_tokens=n,checks={'quality':True},finish_reason='stop',
                             fixture_sha256=str((w,n)),wall_seconds=100*ratio,conversation_wall_seconds=100*ratio)
                        for w,n in BUCKETS]}
    def test_five_pairs_and_regression_gate(self):
        pairs=[(self.record(),self.record(.8+i*.002)) for i in range(5)]
        self.assertTrue(evaluate(pairs)['eligible_to_enable'])
        self.assertFalse(evaluate(pairs[:4])['eligible_to_enable'])
        for _,on in pairs: on['runs'][0]['wall_seconds']=106
        self.assertFalse(evaluate(pairs)['eligible_to_enable'])
    def test_exclude_lost_quality_and_fixture_mismatch(self):
        a,b=self.record(),self.record(.8)
        b['runs'][0]['checks']['quality']=False
        with self.assertRaises(ValueError): evaluate([(a,b)])
    def test_duplicates_settings_environment_and_binary(self):
        a,b=self.record(),self.record(.8)
        b['runs'].append(dict(b['runs'][0]))
        with self.assertRaises(ValueError): evaluate([(a,b)])
        b=self.record(.8); b['profile']['spec']=2
        with self.assertRaises(ValueError): evaluate([(a,b)])
        b=self.record(.8); b['environment']={'STRATA_UNDECLARED':'1'}
        with self.assertRaises(ValueError): evaluate([(a,b)])
        b=self.record(.8); b['launch']={'binary_sha256':'other'}
        with self.assertRaises(ValueError): evaluate([(a,b)])
        b=self.record(.8); b['runs'][0]['wall_seconds']=float('nan')
        with self.assertRaises(ValueError): evaluate([(a,b)])
        b=self.record(.8); b['runs'][0]['fixture_sha256']='different'
        with self.assertRaises(ValueError): evaluate([(a,b)])
if __name__=='__main__': unittest.main()
