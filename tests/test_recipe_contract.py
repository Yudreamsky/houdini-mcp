import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from houdini_mcp_local import sample_geometry,elbow_geometry,recipe_contract


class ContractTests(unittest.TestCase):
    def test_contract_agrees_with_embedded_validator(self):
        for recipe,module in [('pipe_support_sample',sample_geometry),('pipe_elbow_sample',elbow_geometry)]:
            for d,wall,pitch,h in itertools.product((.1,.32,.6),(.002,.02,.03),(.4,.9,2),(.7,1.2)):
                values={k:v[0] for k,v in module.PARAMETERS.items()}
                values.update(diameter=d,wall=wall,support_pitch=pitch,hanger_height=h)
                errors=recipe_contract.violations(recipe,module.PARAMETERS,values)
                try:module.validate(values);accepted=True
                except ValueError:accepted=False
                self.assertEqual(not errors,accepted,(recipe,values,errors))

    def test_reports_multiple_actionable_constraints(self):
        p={k:v[0] for k,v in elbow_geometry.PARAMETERS.items()}
        p.update(diameter=.6,bend_radius=.6,hanger_height=.7,segments=25,support_pitch=2)
        errors=recipe_contract.violations('pipe_elbow_sample',elbow_geometry.PARAMETERS,p)
        self.assertGreaterEqual(len(errors),4)
        radius=next(e for e in errors if e['code']=='bend_radius_ratio')
        self.assertEqual(radius['fields'],['bend_radius','diameter'])
        self.assertAlmostEqual(radius['limit'],.9)

    def test_types_and_nonfinite_values_are_not_rule_inputs(self):
        for key,value in [('diameter',True),('wall',float('nan')),('length','3'),('segments',24.5),('other',1)]:
            p={k:v[0] for k,v in sample_geometry.PARAMETERS.items()};p[key]=value
            errors=recipe_contract.violations('pipe_support_sample',sample_geometry.PARAMETERS,p)
            self.assertTrue(errors,(key,value))
        schema=recipe_contract.parameter_schema(elbow_geometry.PARAMETERS)
        self.assertEqual(schema['bend_segments']['type'],'integer')
        self.assertEqual(schema['bend_radius']['type'],'number')

if __name__=='__main__':unittest.main()
