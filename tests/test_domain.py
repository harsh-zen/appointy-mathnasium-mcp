import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from appointy_mathnasium_mcp import domain


class DomainLogicTests(unittest.TestCase):
    def test_enrolment_booking_status_matches_frontend_style_logic(self):
        now = datetime(2026, 7, 7, tzinfo=timezone.utc)

        self.assertEqual(
            domain._enrolment_booking_status(
                {
                    "startDate": (now + timedelta(days=5)).isoformat(),
                    "terminationDate": (now + timedelta(days=40)).isoformat(),
                },
                now,
            ),
            "active",
        )
        self.assertEqual(
            domain._enrolment_booking_status(
                {
                    "startDate": (now - timedelta(days=40)).isoformat(),
                    "terminationDate": "0001-01-01T00:00:00Z",
                },
                now,
            ),
            "active",
        )
        self.assertEqual(
            domain._enrolment_booking_status(
                {
                    "startDate": (now - timedelta(days=40)).isoformat(),
                    "terminationDate": (now - timedelta(days=1)).isoformat(),
                },
                now,
            ),
            "inactive",
        )


    def test_center_booking_url_prefers_company_slug_for_support(self):
        company = {
            "id": "grp_1/com_gurmeet",
            "displayName": "Gurmeet C",
            "slugObject": {"slugValue": "gurmeetc"},
        }
        location = {
            "id": "grp_1/com_gurmeet/loc_teddington",
            "name": "Teddington UK",
            "customLocationId": "3706",
            "active": True,
            "slugObject": {"slugValue": "mathnasium1947l"},
            "preference": {"timezone": "Europe/London"},
        }

        parsed = domain._parse_location_node(location, company)

        self.assertEqual(parsed["bookingUrl"], "https://mathnasium-booking.appointy.com/gurmeetc")
        self.assertEqual(parsed["bookingUrlLevel"], "company")
        self.assertEqual(parsed["companyBookingUrl"], "https://mathnasium-booking.appointy.com/gurmeetc")
        self.assertEqual(parsed["locationBookingUrl"], "https://mathnasium-booking.appointy.com/mathnasium1947l")
        self.assertEqual(parsed["bookingUrls"][0], "https://mathnasium-booking.appointy.com/gurmeetc")

    def test_resolve_guardian_parent_scope_accepts_short_location_id(self):
        context = {
            "centerIndex": [
                {
                    "companyId": "grp_1/com_1",
                    "locationId": "grp_1/com_1/loc_1",
                }
            ]
        }

        parent, company = domain._resolve_guardian_parent_scope("loc_1", context)

        self.assertEqual(parent, "grp_1/com_1/loc_1")
        self.assertEqual(company, "grp_1/com_1")


class GuardianLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_guardian_supports_explicit_first_and_last_name(self):
        calls = {}
        context = {
            "centerIndex": [
                {
                    "companyId": "grp_01HA9WW1JPRN80YE0DS6ZJJN88/com_1",
                    "locationId": "grp_01HA9WW1JPRN80YE0DS6ZJJN88/com_1/loc_1",
                    "name": "Mathnasium Test",
                    "active": True,
                }
            ],
            "companies": [
                {
                    "companyId": "grp_01HA9WW1JPRN80YE0DS6ZJJN88/com_1",
                    "locations": [],
                }
            ],
        }

        class FakeAppointy:
            async def find_guardians_graphql(self, **kwargs):
                calls["find"] = kwargs
                return {
                    "data": {
                        "customers": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "grp_01HA9WW1JPRN80YE0DS6ZJJN88/com_1/cust_1",
                                        "firstName": "Jason",
                                        "lastName": "Mallet",
                                        "email": "jason@example.com",
                                    }
                                }
                            ]
                        }
                    }
                }

            async def get_guardian_students_detail_graphql(self, **kwargs):
                calls["detail"] = kwargs
                return {
                    "data": {
                        "customerLocationLinks": {"locationIds": []},
                        "students": {"edges": []},
                    }
                }

        async def fake_context(refresh=False):
            return context

        with (
            patch.object(domain, "appointy", FakeAppointy()),
            patch.object(domain, "_get_group_context_cached", fake_context),
            patch.object(domain, "MATHNASIUM_GROUP_ID", "grp_01HA9WW1JPRN80YE0DS6ZJJN88"),
        ):
            result = await domain._find_guardians_internal(
                parent_id="grp_01HA9WW1JPRN80YE0DS6ZJJN88/com_1",
                email=None,
                name=None,
                first_name="Jason",
                last_name="Mallet",
                phone=None,
                center_id=None,
                limit=10,
            )

        self.assertEqual(calls["find"]["first_name"], "Jason")
        self.assertEqual(len(result["matches"]), 1)
        self.assertEqual(result["matches"][0]["name"], "Jason Mallet")
        self.assertEqual(result["matches"][0]["matchReason"], "exact_name")


class EntityLookupTests(unittest.IsolatedAsyncioTestCase):
    async def test_services_include_mathnasium_enrolment_linkage(self):
        class FakeAppointy:
            async def _graphql(self, **kwargs):
                return {
                    "data": {
                        "services": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "grp_1/com_1/loc_1/srv_1",
                                        "title": "In Center",
                                        "active": True,
                                        "durations": [1800, 3600],
                                        "mathnasiumServiceLinks": {
                                            "id": "math_1",
                                            "memberships": [{"id": "mem_33986", "name": "Monthly"}],
                                            "grades": [{"id": "grd_14594", "name": "Grade 6"}],
                                        },
                                        "settings": {
                                            "bookingRules": {
                                                "availabilityType": "AUTOMATIC",
                                                "fixedInterval": 1800,
                                            }
                                        },
                                    }
                                }
                            ]
                        }
                    },
                    "errors": None,
                }

        with patch.object(domain, "appointy", FakeAppointy()):
            result = await domain._get_graphql_entity_internal(
                entity_type="services",
                parent_id="grp_1/com_1/loc_1",
                company_id="grp_1/com_1",
                location_id="grp_1/com_1/loc_1",
                entity_id=None,
                limit=25,
            )

        service = result["items"][0]
        self.assertEqual(service["membershipTypeIds"], ["mem_33986"])
        self.assertEqual(service["gradeRangeIds"], ["grd_14594"])
        self.assertEqual(service["durationsMinutes"], [30.0, 60.0])
        self.assertTrue(service["hasMembershipLinks"])
        self.assertTrue(service["hasGradeRangeLinks"])
        self.assertEqual(service["settings"]["bookingRules"]["availabilityType"], "AUTOMATIC")


if __name__ == "__main__":
    unittest.main()
