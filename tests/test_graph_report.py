"""graph_edit results: short by default, every step on request; and the copy step's schema."""
import json
import unittest

from pydantic import TypeAdapter, ValidationError

from hlab.graph_report import notable, same, summary
from hlab.graph_schema import Copy, Edit, Patch

CLEAN = {"errors": [], "warnings": []}


def placement(i):
    """What one hand-built placement costs: five steps, as in the washer assembly."""
    obj, src = f"/obj/ASM/foot_{i:02d}", f"/obj/ASM/foot_{i:02d}/src"
    ops = [dict(op="create", path=obj, type="geo"), dict(op="create", path=src, type="object_merge"),
           dict(op="set", path=src, parm="objpath1", value="/obj/PARTS/foot/OUT"),
           dict(op="set", path=obj, parm="tx", value=0.03 * i), dict(op="set", path=obj, parm="tz", value=-0.525)]
    rows = [dict(step=0, op="create", path=obj, init_scripts=True, type="Object/geo", **CLEAN),
            dict(step=0, op="create", path=src, init_scripts=True, type="Sop/object_merge", **CLEAN),
            dict(step=0, op="set", path=src, value="/obj/PARTS/foot/OUT", type="Sop/object_merge", **CLEAN),
            dict(step=0, op="set", path=obj, value=0.03 * i, type="Object/geo", **CLEAN),
            dict(step=0, op="set", path=obj, value=-0.525, type="Object/geo", **CLEAN)]
    return ops, rows


class ReportTests(unittest.TestCase):
    def test_values_compare_as_houdini_stores_them(self):
        self.assertTrue(same(1, True))
        self.assertTrue(same(2.0, 2))
        self.assertTrue(same(0.2425, 0.24250000000001))
        self.assertTrue(same("poly", "poly"))
        self.assertFalse(same(0, "poly"))
        self.assertFalse(same("F:/shot/a.bgeo", "$HIP/a.bgeo"))
        self.assertFalse(same({"preview": "f@a", "length": 900, "sha256": "x"}, "f@a..."))

    def test_a_clean_batch_is_a_few_lines(self):
        ops, rows = [], []
        for i in range(24):
            more_ops, more_rows = placement(i)
            ops += more_ops
            rows += more_rows
        for step, row in enumerate(rows, 1):
            row["step"] = step
        result = summary(rows, ops, "MCP: assembly")
        self.assertEqual(result, {"label": "MCP: assembly", "count": 120, "ops": {"create": 48, "set": 72},
                                  "omitted": 120, "steps": []})
        self.assertLess(len(json.dumps(result, indent=2).splitlines()), 40)
        full = summary(rows, ops, "MCP: assembly", verbose=True)
        self.assertEqual((len(full["steps"]), full["omitted"]), (120, 0))
        self.assertGreater(len(json.dumps(full, indent=2).splitlines()), 900)

    def test_only_the_step_with_a_warning_is_listed(self):
        ops, rows = placement(1)
        rows[2]["warnings"] = ["Invalid source /obj/PARTS/foot/OUT"]
        result = summary(rows, ops, "MCP: one warning")
        self.assertEqual(result["steps"], [{**rows[2], "parm": "objpath1"}])
        self.assertEqual((result["count"], result["omitted"]), (5, 4))

    def test_a_step_listed_for_its_value_is_one_short_row(self):
        ops, rows = [], []
        for i in range(49):
            path = f"/obj/ASM/part_{i:02d}"
            if i < 20:
                ops.append(dict(op="set", path=path, parm="tx", value='detail("/obj/DIMS/OUT", "C0", 0)', expression="hscript"))
                rows.append(dict(step=i + 1, op="set", path=path, value=0.45, type="Object/geo", **CLEAN))
            else:
                ops.append(dict(op="set", path=path, parm="tz", value=0.725))
                rows.append(dict(step=i + 1, op="set", path=path, value=0.725, type="Object/geo", **CLEAN))
        result = summary(rows, ops, "MCP: placements")
        self.assertEqual((result["count"], result["omitted"], len(result["steps"])), (49, 29, 20))
        self.assertEqual(result["steps"][0], {"step": 1, "op": "set", "path": "/obj/ASM/part_00", "parm": "tx", "value": 0.45})
        self.assertLess(len(json.dumps(result, indent=2).splitlines()), 160)
        # verbose keeps the full rows
        self.assertEqual(summary(rows, ops, "MCP: placements", verbose=True)["steps"][0], rows[0])

    def test_steps_that_say_something_new_are_listed(self):
        long_text = {"preview": "x" * 120, "length": 900, "sha256": "0"}
        cases = [
            (dict(op="create", path="/obj/EXT", type="probe"), dict(op="create", init_scripts=False), True),
            (dict(op="set", path="/obj/A", parm="tx", value="ch('../B/tx')", expression="hscript"),
             dict(op="set", value=1.5), True),
            (dict(op="set", path="/obj/A", parm="file", value="$HIP/a.bgeo"), dict(op="set", value="F:/shot/a.bgeo"), True),
            (dict(op="set", path="/obj/A/w", parm="snippet", value="x" * 900), dict(op="set", value=long_text), True),
            (dict(op="set", path="/obj/A", parm="on", value=True), dict(op="set", value=1), False),
            (dict(op="flags", path="/obj/A/OUT", display=True), dict(op="flags", display=True, render=False), False),
            (dict(op="flags", path="/obj/A/OUT", display=True, render=True),
             dict(op="flags", display=True, render=False), True),
            (dict(op="connect", path="/obj/A/b", source="/obj/A/a"), dict(op="connect", inputs=["/obj/A/a"]), False),
            (dict(op="rename", path="/obj/A", name="B"), dict(op="rename"), False),
            (dict(op="delete", path="/obj/A"), dict(op="delete"), False),
            (dict(op="copy", source="/obj/A", path="/obj/B", set={"tx": 1.3}), dict(op="copy", values={"tx": 1.3}), False),
            (dict(op="copy", source="/obj/A", path="/obj/B", set={"tx": 1.3}), dict(op="copy", values={"tx": 0.0}), True),
            (dict(op="copy", source="/obj/A", path="/obj/B"), dict(op="copy", values={}), False),
            (dict(op="patch", path="/obj/A/w", parm="snippet", find="0.18", replace="0.10"),
             dict(op="patch", value=long_text), False),
        ]
        for op, row, expected in cases:
            with self.subTest(op=op):
                self.assertIs(notable({**CLEAN, **row}, op), expected)


class CopySchemaTests(unittest.TestCase):
    def test_copy_is_one_step_with_its_values(self):
        sent = dict(op="copy", source="/obj/ASM/foot_01", path="/obj/ASM/foot_02", set={"tx": 0.03, "tz": -0.525})
        step = TypeAdapter(Edit).validate_python(sent)
        self.assertIsInstance(step, Copy)
        self.assertEqual(step.model_dump(exclude_unset=True), sent)
        bare = dict(op="copy", source="/obj/A", path="/obj/B")
        self.assertEqual(TypeAdapter(Edit).validate_python(bare).model_dump(exclude_unset=True), bare)

    def test_copy_refuses_what_it_cannot_write(self):
        for bad in (dict(op="copy", path="/obj/B"),
                    dict(op="copy", source="/obj/A", path="/obj/B", set={"tx": [1, 2]}),
                    dict(op="copy", source="/obj/A", path="/obj/B", set={f"p{i}": i for i in range(33)}),
                    dict(op="copy", source="/obj/A", path="/obj/B", expression="python")):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                TypeAdapter(Edit).validate_python(bad)


class PatchSchemaTests(unittest.TestCase):
    def test_patch_names_a_fragment_and_how_often_it_occurs(self):
        sent = dict(op="patch", path="/obj/A/w", parm="snippet", find="pitch*0.18", replace="pitch*0.10")
        step = TypeAdapter(Edit).validate_python(sent)
        self.assertIsInstance(step, Patch)
        self.assertEqual((step.count, step.model_dump(exclude_unset=True)), (1, sent))
        self.assertEqual(TypeAdapter(Edit).validate_python({**sent, "replace": "", "count": 3}).count, 3)
        for bad in ({**sent, "find": ""}, {**sent, "count": 0}, {**sent, "count": 65},
                    {k: v for k, v in sent.items() if k != "replace"}, {**sent, "value": "x"}):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                TypeAdapter(Edit).validate_python(bad)


if __name__ == "__main__":
    unittest.main()
