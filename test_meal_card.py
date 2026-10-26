"""Regression tests use an isolated database; no group messages or real preferences are changed."""
import contextlib
import io
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import meal_card as meal
meal.CHAT = "test-chat"
meal.MEMBERS = {"test-member-a", "test-member-b"}

class MealFlow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = patch.object(meal, 'ROOT', pathlib.Path(self.temp.name)); self.root.start()
        self.api = patch.object(meal, 'cli', return_value={}); self.mock_api = self.api.start()
        self.counter = 0
        with meal.db() as c:
            c.execute('INSERT INTO cards(message_id,result,meta_json) VALUES (?,?,?)',
                      ('test-card', None, json.dumps({'day':'2026-10-26','meal':'lunch'})))

    def tearDown(self):
        self.api.stop(); self.root.stop(); self.temp.cleanup()

    def event(self, action, **fields):
        self.counter += 1
        event = {'chat_id':meal.CHAT, 'operator_id':next(iter(meal.MEMBERS)), 'card_content':'test',
                 'message_id':'test-card', 'event_id':str(self.counter), 'token':'local-test-token',
                 'action_value':json.dumps({'app':meal.APP,'action':action,**fields})}
        with contextlib.redirect_stdout(io.StringIO()): meal.handle(event)
        return event

    def result(self):
        with meal.db() as c:
            value = c.execute('SELECT result FROM cards WHERE message_id="test-card"').fetchone()[0]
            return json.loads(value) if value else None

    def options(self):
        with meal.db() as c: return meal.current(c)

    def save(self, value, pool='all'):
        self.counter += 1
        event = {'chat_id':meal.CHAT,'operator_id':next(iter(meal.MEMBERS)),'card_content':'test',
                 'message_id':'test-card','event_id':str(self.counter),'token':'local-test-token',
                 'action_name':'save_meal_settings','form_value':json.dumps({'excluded':value,'pool':pool})}
        with contextlib.redirect_stdout(io.StringIO()):meal.handle(event)

    def test_50_dishes_and_filtering(self):
        self.assertEqual(len({d['name'] for d in meal.MENU}),50)
        self.save('虾,虾、牛肉')
        self.assertEqual(self.options()['excluded'],'虾、牛肉')
        for _ in range(10):
            self.event('draw'); dish=self.result()
            self.assertNotIn('虾',dish['name']+dish['ingredients'])
            self.assertNotIn('牛肉',dish['name']+dish['ingredients'])

    def test_draws_do_not_immediately_repeat(self):
        names=[]
        for _ in range(5):self.event('draw');names.append(self.result()['name'])
        self.assertEqual(len(set(names)),5)

    def test_confirmation_is_idempotent_and_can_change(self):
        self.event('draw');name=self.result()['name']
        event=self.event('confirm',expected_dish=name)
        with contextlib.redirect_stdout(io.StringIO()):meal.handle(event)
        self.assertEqual(len(self.options()['recent']),1)
        self.assertEqual(self.options()['recent'][0]['dish']['name'],name)
        self.event('draw')
        self.assertEqual(len(self.options()['recent']),0)

    def test_stale_confirmation_does_not_confirm_another_dish(self):
        self.event('draw');first=self.result()['name']
        self.event('draw');self.event('confirm',expected_dish=first)
        self.assertEqual(len(self.options()['recent']),0)
        self.assertIn('卡片刚刚更新',self.mock_api.call_args.args[4])

    def test_favorites_pool_and_toggle(self):
        self.event('draw');name=self.result()['name']
        self.event('favorite',expected_dish=name)
        self.save('',pool='favorites');self.event('draw')
        self.assertEqual(self.result()['name'],name)
        self.event('favorite',expected_dish=name)
        self.assertEqual(self.options()['favorites'],[])
        self.event('draw')
        self.assertIn('没有符合',self.mock_api.call_args.args[4])
        self.event('use_all');self.event('draw');self.assertIsNotNone(self.result())

    def test_empty_preference_and_all_excluded(self):
        self.save('虾');self.save('');self.assertEqual(self.options()['excluded'],'')
        # A term appearing in every menu name is not assumed; directly exercise the empty set.
        with patch.object(meal,'MENU',[{'name':'番茄饭','ingredients':'番茄,米饭'}]):
            self.save('番茄');self.event('draw')
            self.assertIn('没有符合',self.mock_api.call_args.args[4])

    def test_callback_failure_rolls_back(self):
        self.mock_api.side_effect=RuntimeError('test failure')
        with self.assertRaises(RuntimeError):self.event('draw')
        self.assertIsNone(self.result())
        with meal.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_unauthorized_member_cannot_mutate(self):
        meal.handle({'chat_id':meal.CHAT,'operator_id':'not-a-member','card_content':'test','token':'test','event_id':'x'})
        self.mock_api.assert_not_called()

    def test_legacy_database_migration_preserves_preferences(self):
        legacy=pathlib.Path(self.temp.name)/'legacy';legacy.mkdir()
        with sqlite3.connect(legacy/'meal_card.sqlite') as c:
            c.executescript('CREATE TABLE cards (message_id TEXT PRIMARY KEY,result TEXT); CREATE TABLE prefs(chat_id TEXT PRIMARY KEY,excluded TEXT NOT NULL);')
            c.execute('INSERT INTO prefs VALUES (?,?)',(meal.CHAT,'花生'))
        with patch.object(meal,'ROOT',legacy):
            with meal.db() as c:self.assertEqual(meal.current(c)['excluded'],'花生')

if __name__=='__main__':unittest.main()
