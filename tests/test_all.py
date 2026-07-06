import os
import sys
import unittest
from datetime import datetime, date, timedelta
from sqlalchemy import text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db_manager import SessionLocal, engine
from allocation.allocation_engine import haversine_distance, generate_transfer_recommendations, BLOOD_COMPATIBILITY
from expiry.expiry_tracker import get_expiry_alerts

class TestBloodBankSystem(unittest.TestCase):
    
    def test_haversine_distance(self):
        """Test the Haversine formula calculation for geographical distances."""
        # Distance from City General to St. Jude should be very close (~0.8-1.0 miles)
        lat1, lon1 = 40.7128, -74.0060
        lat2, lon2 = 40.7250, -74.0100
        dist = haversine_distance(lat1, lon1, lat2, lon2)
        self.assertGreater(dist, 0.5)
        self.assertLess(dist, 1.5)
        
    def test_blood_compatibility(self):
        """Test compatibility mappings (e.g. O- is universal donor, AB+ is universal recipient)."""
        self.assertIn('A+', BLOOD_COMPATIBILITY['O-'])
        self.assertIn('O+', BLOOD_COMPATIBILITY['O-'])
        self.assertIn('AB+', BLOOD_COMPATIBILITY['A+'])
        self.assertNotIn('O-', BLOOD_COMPATIBILITY['A+']) # A+ cannot donate to O-
        
    def test_database_connection(self):
        """Test that the database connection is active and schemas are queried successfully."""
        session = SessionLocal()
        try:
            # Query hospitals count
            res = session.execute(text("SELECT COUNT(*) FROM hospitals")).scalar()
            self.assertEqual(res, 8) # We seeded 8 hospitals
            
            # Query components count
            res_comp = session.execute(text("SELECT COUNT(*) FROM blood_components")).scalar()
            self.assertEqual(res_comp, 4) # 4 components
        finally:
            session.close()
            
    def test_expiry_alerts(self):
        """Test that the expiry tracker correctly processes alerts."""
        # Run expiry check on simulation anchor date
        anchor = date(2026, 7, 5)
        alerts = get_expiry_alerts(anchor)
        self.assertIsInstance(alerts, list)
        self.assertGreater(len(alerts), 0)
        
        # Check content structure of alerts
        first_alert = alerts[0]
        self.assertIn('inventory_id', first_alert)
        self.assertIn('severity', first_alert)
        self.assertIn('message', first_alert)
        self.assertIn('units', first_alert)
        
    def test_allocation_transfer_recs(self):
        """Test that the allocation engine correctly generates recommendations."""
        anchor = date(2026, 7, 5)
        recs = generate_transfer_recommendations(anchor)
        self.assertIsInstance(recs, list)
        
        # If there are recommendations, verify score structures
        if recs:
            first_rec = recs[0]
            self.assertIn('source_hospital_name', first_rec)
            self.assertIn('destination_hospital_name', first_rec)
            self.assertIn('units_to_transfer', first_rec)
            self.assertIn('transfer_score', first_rec)
            self.assertGreaterEqual(first_rec['transfer_score'], -100) # reasonable range

if __name__ == "__main__":
    unittest.main()
