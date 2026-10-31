"""Saved Character Studio reference workflow contracts."""

from __future__ import annotations
import json
from pathlib import Path
import unittest

PACKAGE = Path(__file__).resolve().parents[1]


class WorkflowContractTests(unittest.TestCase):
    def test_reference_examples_use_production_settings(self):
        for name in (
            "Anchored Reference - Single Pass API.json",
            "Text Scoped Reference - Single Pass API.json",
            "Character Studio - Reference API.json",
        ):
            with self.subTest(name=name):
                graph = json.loads((PACKAGE / "example_workflows" / name).read_text())
                kinds = {n["class_type"]: n["inputs"] for n in graph.values()}
                self.assertEqual(
                    kinds["LoraLoaderModelOnly"]["lora_name"],
                    "moss/MOSS-Character-Studio-Reference-BF16.safetensors",
                )
                self.assertEqual(kinds["LoraLoaderModelOnly"]["strength_model"], 1.0)
                self.assertEqual(kinds["ModelSamplingAuraFlow"]["shift"], 5.0)
                self.assertEqual(kinds["ModelSamplingAuraFlow"]["sampling"], "flow")
                self.assertNotIn("ModelSamplingSD3", kinds)
                self.assertEqual(
                    kinds["SkipLayerGuidanceDiTSimple"]["single_layers"], "22"
                )
                for key, value in dict(
                    steps=25,
                    cfg=3.0,
                    sampler_name="euler",
                    scheduler="sgm_uniform",
                    seed=42,
                ).items():
                    self.assertEqual(kinds["KSampler"][key], value)
                for node in graph.values():
                    if node["class_type"] == "MOSSAnchoredReferenceEncode":
                        for key, value in dict(
                            anchor_mode="full_portrait_panel",
                            panel_scoped_text=True,
                            reference_framing="auto_portrait",
                            mask_text_self_attention=False,
                            mask_text_embedder=False,
                        ).items():
                            self.assertEqual(node["inputs"][key], value)
                for node in graph.values():
                    for value in node["inputs"].values():
                        if isinstance(value, list):
                            self.assertIn(value[0], graph)

    def check_ui_matches_api_inputs_and_routes(self, stem):
        graph = json.loads(
            (PACKAGE / "example_workflows" / (stem + " API.json")).read_text()
        )
        ui = json.loads((PACKAGE / "example_workflows" / (stem + ".json")).read_text())
        links = {link[0]: link for link in ui["links"]}
        self.assertEqual({str(n["id"]) for n in ui["nodes"]}, set(graph))
        for node in ui["nodes"]:
            expected = graph[str(node["id"])]
            self.assertEqual(node["type"], expected["class_type"])
            values = {
                k: v
                for k, v in node.get("widgets_values_named", {}).items()
                if k in expected["inputs"]
            }
            for socket in node["inputs"]:
                if socket["link"] is not None:
                    link = links[socket["link"]]
                    values[socket["name"]] = [str(link[1]), link[2]]
            self.assertEqual(values, expected["inputs"])

    def test_all_reference_ui_graphs_match_api_inputs_and_routes(self):
        for stem in (
            "Anchored Reference - Single Pass",
            "Text Scoped Reference - Single Pass",
            "Character Studio - Reference",
        ):
            with self.subTest(stem=stem):
                self.check_ui_matches_api_inputs_and_routes(stem)


if __name__ == "__main__":
    unittest.main()
