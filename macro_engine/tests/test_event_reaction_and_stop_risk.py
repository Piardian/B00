import unittest
from calibration.event_reaction_and_stop_risk import reaction_state,cross_asset_confirmation,stop_risk_diagnostics,evaluate_pre_registered_filter

class EventReactionAndStopRiskTests(unittest.TestCase):
    def test_persistent_reaction(self):
        r=reaction_state(0,5,4,6,3,1);self.assertEqual(r["state"],"PERSISTENT");self.assertEqual(r["persistence_bars"],4)
    def test_reversal_reaction(self):
        r=reaction_state(2,-3,-2,1,2,1);self.assertEqual(r["state"],"REVERSAL");self.assertTrue(r["reversal"])
    def test_cross_asset_confirmation(self):
        r=cross_asset_confirmation({"DXY":1,"EURUSD":-2,"XAUUSD":-1},{"DXY":1,"EURUSD":-1,"XAUUSD":-1});self.assertTrue(r["coherent"]);self.assertEqual(r["confirmation_ratio"],1.0)
    def test_stop_risk_is_diagnostic_only(self):
        r=stop_risk_diagnostics(entry_to_poi_bps=12,atr_bps=20,adverse_excursion_bps=-30,event_freeze_active=True,setup_age_bars=10,stale_after_bars=8,pre_event_move_bps=40);self.assertEqual(r["mae_to_atr"],1.5);self.assertTrue(r["stale"])
    def test_filter_is_pre_registered_and_non_activating(self):
        r=evaluate_pre_registered_filter({"event_freeze_active":True,"cross_asset_coherent":False});self.assertTrue(r["no_trade"]);self.assertFalse(r["production_activation"])

if __name__=="__main__":unittest.main()
