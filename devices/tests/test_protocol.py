"""
Tests de la couche protocole TM20 (parsing, validation, construction, temps).

Logique pure et sans base de données : SimpleTestCase.
"""

from datetime import datetime

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from devices.protocol import (
    TM20Parser,
    MessageValidator,
    ValidationError,
    ResponseBuilder,
    CommandBuilder,
    make_terminal_aware,
    terminal_now_str,
)
from devices.protocol.parser import ParseError


class ParserTests(SimpleTestCase):
    def test_parse_json_accepts_str_and_bytes(self):
        self.assertEqual(TM20Parser.parse_json('{"cmd":"reg"}'), {"cmd": "reg"})
        self.assertEqual(TM20Parser.parse_json(b'{"cmd":"reg"}'), {"cmd": "reg"})

    def test_parse_json_invalid_raises(self):
        with self.assertRaises(ParseError):
            TM20Parser.parse_json("{not json}")

    def test_serialize_roundtrip(self):
        payload = {"cmd": "opendoor", "door": 1, "delay": 5}
        self.assertEqual(TM20Parser.parse_json(TM20Parser.serialize(payload)), payload)

    def test_parse_register_exposes_model_and_firmware(self):
        msg = {
            "cmd": "reg",
            "sn": "ZX0006827500",
            "cpusn": "123456789",
            "devinfo": {"modelname": "tfs30", "firmware": "th600w v6.1"},
        }
        reg = TM20Parser.parse_register(msg)
        self.assertEqual(reg.sn, "ZX0006827500")
        self.assertEqual(reg.model, "tfs30")
        self.assertEqual(reg.firmware, "th600w v6.1")

    def test_parse_register_without_devinfo(self):
        reg = TM20Parser.parse_register({"cmd": "reg", "sn": "TEST001"})
        self.assertEqual(reg.model, "")
        self.assertEqual(reg.firmware, "")

    def test_parse_sendlog_builds_records(self):
        msg = {
            "cmd": "sendlog",
            "sn": "SN123",
            "count": 2,
            "logindex": 10,
            "record": [
                {"enrollid": 1, "time": "2024-01-15 10:30:00", "mode": 0, "inout": 0},
                {"enrollid": 2, "time": "2024-01-15 10:31:00", "mode": 8, "inout": 1},
            ],
        }
        parsed = TM20Parser.parse_sendlog(msg)
        self.assertEqual(parsed.count, 2)
        self.assertEqual(parsed.logindex, 10)
        self.assertEqual(len(parsed.records), 2)
        self.assertEqual(parsed.records[0].enrollid, 1)
        self.assertEqual(parsed.records[1].inout, 1)

    def test_parse_datetime(self):
        self.assertEqual(
            TM20Parser.parse_datetime("2024-01-15 10:30:00"),
            datetime(2024, 1, 15, 10, 30, 0),
        )
        self.assertIsNone(TM20Parser.parse_datetime(""))
        self.assertIsNone(TM20Parser.parse_datetime("not-a-date"))


class ValidatorTests(SimpleTestCase):
    def test_valid_reg(self):
        self.assertTrue(MessageValidator.validate({"cmd": "reg", "sn": "TEST001"}))

    def test_missing_command_raises(self):
        with self.assertRaises(ValidationError):
            MessageValidator.validate({"foo": "bar"})

    def test_reg_empty_sn_raises(self):
        with self.assertRaises(ValidationError):
            MessageValidator.validate({"cmd": "reg", "sn": ""})

    def test_reg_short_sn_raises(self):
        with self.assertRaises(ValidationError):
            MessageValidator.validate({"cmd": "reg", "sn": "abc"})

    def test_sendlog_missing_record_raises(self):
        with self.assertRaises(ValidationError):
            MessageValidator.validate({"cmd": "sendlog", "sn": "SN123", "count": 0})

    def test_senduser_invalid_backupnum_raises(self):
        with self.assertRaises(ValidationError):
            MessageValidator.validate(
                {"cmd": "senduser", "enrollid": 1, "backupnum": 99}
            )

    def test_senduser_valid_face(self):
        self.assertTrue(
            MessageValidator.validate(
                {"cmd": "senduser", "enrollid": 1, "backupnum": 20, "admin": 0}
            )
        )

    def test_response_requires_result(self):
        with self.assertRaises(ValidationError):
            MessageValidator.validate({"ret": "reg"})
        self.assertTrue(MessageValidator.validate({"ret": "reg", "result": True}))

    def test_is_valid_never_raises(self):
        self.assertFalse(MessageValidator.is_valid({"cmd": "reg", "sn": ""}))
        self.assertTrue(MessageValidator.is_valid({"cmd": "reg", "sn": "TEST001"}))


class BuilderTests(SimpleTestCase):
    def test_response_reg_success(self):
        resp = ResponseBuilder.reg(success=True)
        self.assertEqual(resp["ret"], "reg")
        self.assertTrue(resp["result"])
        self.assertIn("cloudtime", resp)
        self.assertTrue(resp["nosenduser"])

    def test_response_reg_failure(self):
        resp = ResponseBuilder.reg(success=False, reason="nope")
        self.assertFalse(resp["result"])
        self.assertEqual(resp["reason"], "nope")
        self.assertNotIn("cloudtime", resp)

    def test_response_sendlog_success(self):
        resp = ResponseBuilder.sendlog(success=True, count=3, logindex=7, access=1)
        self.assertEqual(resp["ret"], "sendlog")
        self.assertEqual(resp["count"], 3)
        self.assertEqual(resp["logindex"], 7)
        self.assertEqual(resp["access"], 1)

    def test_command_opendoor(self):
        self.assertEqual(
            CommandBuilder.opendoor(door=2, delay=10),
            {"cmd": "opendoor", "door": 2, "delay": 10},
        )

    def test_command_setuserinfo(self):
        cmd = CommandBuilder.setuserinfo(
            enrollid=1, name="John", backupnum=0, admin=1, record="data"
        )
        self.assertEqual(cmd["cmd"], "setuserinfo")
        self.assertEqual(cmd["enrollid"], 1)
        self.assertEqual(cmd["name"], "John")
        self.assertEqual(cmd["admin"], 1)

    def test_command_deleteuser_default_all(self):
        self.assertEqual(CommandBuilder.deleteuser(enrollid=5)["backupnum"], 13)

    def test_command_settime_uses_now(self):
        cmd = CommandBuilder.settime()
        self.assertEqual(cmd["cmd"], "settime")
        self.assertRegex(cmd["cloudtime"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


class TerminalTimeTests(SimpleTestCase):
    def test_make_terminal_aware_none(self):
        self.assertIsNone(make_terminal_aware(None))

    def test_make_terminal_aware_naive_becomes_aware(self):
        naive = datetime(2024, 1, 15, 10, 30, 0)
        aware = make_terminal_aware(naive)
        self.assertTrue(timezone.is_aware(aware))

    def test_make_terminal_aware_keeps_aware_unchanged(self):
        already = timezone.now()
        self.assertEqual(make_terminal_aware(already), already)

    def test_terminal_timezone_offset_applied(self):
        from django.conf import settings

        overridden = {**settings.TM20_SETTINGS, "TERMINAL_TIMEZONE": "Africa/Kigali"}
        with override_settings(TM20_SETTINGS=overridden):
            aware = make_terminal_aware(datetime(2024, 1, 15, 10, 30, 0))
            # Africa/Kigali = UTC+2 (offset fixe)
            self.assertEqual(aware.utcoffset().total_seconds(), 2 * 3600)

    def test_terminal_now_str_format(self):
        self.assertRegex(
            terminal_now_str(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"
        )
