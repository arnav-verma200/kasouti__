import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import os
import json
import main

class TestAgents(unittest.TestCase):
    def setUp(self):
        # Reset state to seeds before each test
        main.state.clear()
        main.state.update(main.get_initial_state())
        # Disable rates feed offline check by default
        main.state["spot"]["feed_online"] = True
        
        # Patch notion_sync to prevent real network calls
        from unittest.mock import AsyncMock
        self.notion_sync_patcher = patch('notion_sync.sync_order_to_notion', new_callable=AsyncMock)
        self.notion_update_patcher = patch('notion_sync.update_ledger_row_status_async', new_callable=AsyncMock)
        self.mock_notion_sync = self.notion_sync_patcher.start()
        self.mock_notion_update = self.notion_update_patcher.start()
        
    def tearDown(self):
        self.notion_sync_patcher.stop()
        self.notion_update_patcher.stop()
        
    def test_pydantic_schema_validation(self):
        """Schema validation: ensure mock outputs conform to models"""
        # 1. SalesDraft
        sales_json = '{"metal": "Gold", "karat_or_purity": "22K", "weight_g": 10.5, "complexity": "medium", "technique": "filigree", "gemstone": "Ruby", "proposed_price": 1200.0, "rationale": "High quality filigree ring"}'
        sales = main.SalesDraft.model_validate_json(sales_json)
        self.assertEqual(sales.metal, "Gold")
        
        # 2. CostingValidation
        costing_json = '{"true_cost": 800.0, "margin_ok": true, "suggested_price": 941.18, "pushback_needed": false, "rationale": "Metal and stones calculations show good margin"}'
        costing = main.CostingValidation.model_validate_json(costing_json)
        self.assertTrue(costing.margin_ok)
        
        # 3. ProductionValidation
        production_json = '{"feasible": true, "assigned_artisan": "Shankar Das", "estimated_days": 6, "rationale": "Artisan has low backlog"}'
        prod = main.ProductionValidation.model_validate_json(production_json)
        self.assertTrue(prod.feasible)
        
        # 4. NegotiationTurn
        turn_json = '{"round": 1, "agent": "Sales", "turn_type": "proposal", "text": "Proposing standard price", "timestamp": "2026-07-25T10:00:00"}'
        turn = main.NegotiationTurn.model_validate_json(turn_json)
        self.assertEqual(turn.agent, "Sales")

    def test_startup_fallback(self):
        """Startup fallback: no GEMINI_API_KEY -> full order completes via rule-based path, no crash"""
        # Backup global client
        orig_client = main.gemini_client
        main.gemini_client = None
        
        payload = {
            "customer_name": "Test Customer",
            "metal": "Gold",
            "karat_or_purity": "22K",
            "weight_g": 10.0,
            "budget": 2000.0,
            "deadline_days": 15,
            "complexity": "medium",
            "technique": "filigree",
            "gemstone": "None",
            "size": "Standard",
            "finish": "High Polish"
        }
        
        req = main.IntakeRequest(**payload)
        res = main.post_intake(req)
        
        self.assertEqual(res["status"], "pending")
        self.assertIn("Trust below 0.85 gate", res["reason"])
        
        # Verify negotiation log contains rule-based fallbacks
        pending = main.state["pending"]
        self.assertIsNotNone(pending)
        self.assertIn("negotiation_log", pending)
        log = pending["negotiation_log"]
        self.assertGreaterEqual(len(log), 3)
        self.assertTrue(any(t["turn_type"] == "fallback" for t in log))
        
        # Restore client
        main.gemini_client = orig_client

    @patch('main.gemini_client')
    def test_per_call_fallback(self, mock_gemini):
        """Per-call fallback: mock a single agent call raising an exception mid-order"""
        # Mock Client response
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "metal": "Gold",
            "karat_or_purity": "22K",
            "weight_g": 10.0,
            "complexity": "medium",
            "technique": "filigree",
            "gemstone": "None",
            "proposed_price": 1000.0,
            "rationale": "LLM Sales Proposal"
        })
        
        # Sales succeeds, but Costing raises exception
        def side_effect(model, contents, config):
            if "SalesDraft" in str(config.response_schema):
                return mock_response
            else:
                raise Exception("API Rate Limit Exceeded")
                
        mock_gemini.models.generate_content.side_effect = side_effect
        
        payload = {
            "customer_name": "Test Customer Fallback",
            "metal": "Gold",
            "karat_or_purity": "22K",
            "weight_g": 10.0,
            "budget": 1000.0,
            "deadline_days": 15,
            "complexity": "medium",
            "technique": "filigree",
            "gemstone": "None",
            "size": "Standard"
        }
        
        req = main.IntakeRequest(**payload)
        res = main.post_intake(req)
        
        pending = main.state["pending"]
        self.assertIsNotNone(pending)
        log = pending["negotiation_log"]
        costing_turns = [t for t in log if t["agent"] == "Costing"]
        self.assertTrue(any(t["turn_type"] == "fallback" for t in costing_turns))

    @patch('main.gemini_client')
    def test_round_cap(self, mock_gemini):
        """Round cap: mock Costing rejecting the Sales price twice in a row"""
        sales_resp = MagicMock()
        sales_resp.text = json.dumps({
            "metal": "Gold",
            "karat_or_purity": "22K",
            "weight_g": 10.0,
            "complexity": "medium",
            "technique": "filigree",
            "gemstone": "None",
            "proposed_price": 500.0,
            "rationale": "Proposing low price"
        })
        
        costing_resp = MagicMock()
        costing_resp.text = json.dumps({
            "true_cost": 800.0,
            "margin_ok": False,
            "suggested_price": 1000.0,
            "pushback_needed": True,
            "rationale": "Costing pushback: Margin deficit"
        })
        
        prod_resp = MagicMock()
        prod_resp.text = json.dumps({
            "feasible": True,
            "assigned_artisan": "Shankar Das",
            "estimated_days": 6,
            "rationale": "Timeline is feasible"
        })
        
        def side_effect(model, contents, config):
            schema = str(config.response_schema)
            if "SalesDraft" in schema:
                return sales_resp
            elif "CostingValidation" in schema:
                return costing_resp
            else:
                return prod_resp
                
        mock_gemini.models.generate_content.side_effect = side_effect
        
        payload = {
            "customer_name": "Test Customer Cap Hit",
            "metal": "Gold",
            "karat_or_purity": "22K",
            "weight_g": 10.0,
            "budget": 500.0,
            "deadline_days": 15,
            "complexity": "medium",
            "technique": "filigree",
            "gemstone": "None",
            "size": "Standard"
        }
        
        req = main.IntakeRequest(**payload)
        res = main.post_intake(req)
        
        pending = main.state["pending"]
        self.assertIsNotNone(pending)
        log = pending["negotiation_log"]
        
        costing_rounds = [t["round"] for t in log if t["agent"] == "Costing"]
        self.assertEqual(costing_rounds, [1, 2])
        
        system_turns = [t for t in log if t["agent"] == "System" and t["turn_type"] == "cap_hit"]
        self.assertEqual(len(system_turns), 1)
        self.assertIn("Negotiation Cap Hit", system_turns[0]["text"])

    def test_trust_threshold_consistency(self):
        """Trust threshold consistency: confirm only 0.85 remains anywhere trust is compared or displayed"""
        for filepath in ["main.py", "static/app.js"]:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                # Ensure no old 0.80 thresholds exist for trust score comparison
                self.assertNotIn("0.80", content)
                self.assertNotIn("score >= 0.8 ", content)
                self.assertNotIn("trust >= 0.8 ", content)
                self.assertTrue("0.85" in content)

    def test_notion_disabled_fallback(self):
        """Notion disabled fallback: verify NOTION_ENABLED is False if env keys are missing"""
        import notion_sync
        # Check if environment is actually missing Notion tokens (which it is)
        # and verify NOTION_ENABLED reflects this
        if not all(os.environ.get(k) for k in [
            "SALES_NOTION_TOKEN", "SALES_DATABASE_ID",
            "COSTING_NOTION_TOKEN", "COSTING_DATABASE_ID",
            "PRODUCTION_NOTION_TOKEN", "PRODUCTION_DATABASE_ID",
            "ORCHESTRATOR_NOTION_TOKEN", "ORCHESTRATOR_DATABASE_ID"
        ]):
            self.assertFalse(notion_sync.NOTION_ENABLED)

    @patch('notion_sync.NOTION_ENABLED', True)
    @patch('httpx.AsyncClient.post', new_callable=AsyncMock)
    def test_notion_formatting(self, mock_post):
        """Notion formatting: check formatting rules and page creation payload structures"""
        self.notion_sync_patcher.stop()
        try:
            import notion_sync
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"url": "https://www.notion.so/test-page-url"}
            mock_post.return_value = mock_resp
            
            order_details = {
                "customer_name": "Maharani Laxmi",
                "metal": "Gold",
                "karat_or_purity": "22K",
                "weight_g": 15.0,
                "proposed_price": 1500.0,
                "true_cost": 1000.0,
                "suggested_price": 1176.47,
                "artisan": "Shankar Das",
                "estimated_days": 5,
                "deadline_days": 10,
                "complexity": "medium",
                "technique": "filigree",
                "gemstone": "Ruby",
                "is_custom": False,
                "status": "AUTO_CONFIRMED",
                "net_margin": 0.3333,
                "workshop_notes": "Beautiful gold ring proposal.",
                "feasibility_note": "Production is feasible and schedule fits."
            }
            
            import asyncio
            asyncio.run(notion_sync.sync_order_to_notion("KAS-1002", order_details))
            
            self.assertEqual(mock_post.call_count, 4)
            
            # Index 3 is the Ledger post
            args, kwargs = mock_post.call_args_list[3]
            payload = kwargs.get("json", {})
            properties = payload.get("properties", {})
            
            self.assertEqual(properties["Order ID"]["title"][0]["text"]["content"], "KAS-1002")
            
            summary_text = properties["Negotiation Summary"]["rich_text"][0]["text"]["content"]
            self.assertNotIn("{", summary_text)
            self.assertNotIn("proposed_price", summary_text)
            self.assertIn("Sales proposed $1500.00 against true cost $1000.00", summary_text)
            self.assertEqual(properties["Sales Link"]["url"], "https://www.notion.so/test-page-url")
        finally:
            self.notion_sync_patcher.start()

if __name__ == '__main__':
    unittest.main()
