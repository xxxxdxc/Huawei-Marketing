"""Isolated image policy regressions, no provider calls."""
import copy,unittest
from backend.test_workflow import prepared
from backend import workflow as w

class ImageCountPolicyTests(unittest.TestCase):
    def fixture(self,count):
        t=prepared();t['platform']=t['brief']['platform']='xiaohongshu'
        sections=[];paragraphs=[];images=[]
        for i in range(max(count,1)):
            image_id=f'{i:020d}' if i<count else None
            sec=copy.deepcopy(t['plan']['sections'][0]);sec.update(id=f'P{i}',image_id=image_id)
            para=copy.deepcopy(t['document']['paragraphs'][0]);para.update(section_id=sec['id'],image_id=image_id)
            sections.append(sec);paragraphs.append(para)
            if image_id:images.append(dict(id=image_id,model_verified=True,visual_checked=True,usable=True))
        t['plan']['sections']=sections;t['document']['paragraphs']=paragraphs;t['package']['images']=images
        return t

    def test_recommendation_is_separate_from_hard_bounds(self):
        policy=w.PLATFORMS['xiaohongshu']
        self.assertEqual(policy['recommended_images'],[3,6])
        self.assertEqual(policy['min_images'],1)
        self.assertIsNone(policy['max_images'])
        for count in (1,2,3,6,7,12):
            with self.subTest(count=count):
                t=self.fixture(count)
                w.validate_plan(t,t['plan'])
                self.assertEqual(w.record_user_image_edits(t,t['document']),{})
                self.assertFalse([i for i in w.deterministic_review(t) if i['location']=='配图方案'])

    def test_zero_images_remain_blocked(self):
        t=self.fixture(0)
        with self.assertRaisesRegex(ValueError,'至少1张'):w.validate_plan(t,t['plan'])
        with self.assertRaisesRegex(ValueError,'至少1张'):w.record_user_image_edits(t,t['document'])
        self.assertTrue([i for i in w.deterministic_review(t) if i['location']=='配图方案'])

    def test_other_platforms_keep_hard_bounds(self):
        for platform,low,high in [('wechat',2,4),('moments',1,3)]:
            policy=w.PLATFORMS[platform]
            self.assertIsNotNone(w.image_count_error(policy,low-1))
            self.assertIsNone(w.image_count_error(policy,low))
            self.assertIsNotNone(w.image_count_error(policy,high+1))

    def test_unknown_or_duplicate_images_still_block(self):
        t=self.fixture(2)
        t['plan']['sections'][1]['image_id']='missing'
        with self.assertRaises(ValueError):w.validate_plan(t,t['plan'])
        t['plan']['sections'][1]['image_id']=t['plan']['sections'][0]['image_id']
        with self.assertRaises(ValueError):w.validate_plan(t,t['plan'])

    def test_exact_legacy_policy_hash_remains_valid_but_fact_changes_do_not(self):
        from backend import content_planner as cp
        t=self.fixture(2)
        legacy=dict(w.PLATFORMS['xiaohongshu'],min_images=3,max_images=6)
        legacy.pop('recommended_images');legacy.pop('image_count_note')
        old=cp.digest(cp.shared_context(t,legacy))
        self.assertTrue(cp.candidate_context_matches(t,old))
        t['package']['facts'][0]['claim']='changed actual fact'
        self.assertFalse(cp.candidate_context_matches(t,old))
