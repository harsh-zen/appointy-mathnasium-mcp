"""Read-only QA MCP transport smoke. Requires the standard QA API-key environment.

Run: PYTHONPATH=src python3 scripts/live_qa_smoke.py
Starts/stops a local server on 8137. Captured responses stay in /private/tmp,
not version control. GCP credentials are independent and may be unavailable.
"""

import sys, subprocess, logging, os
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

suite = sys.modules[__name__]
import asyncio, json
from pathlib import Path
from appointy_mathnasium_mcp.tools import (
    mathnasium_get_entity as read,
    mathnasium_find_appointments as apps,
)
from appointy_mathnasium_mcp.tools import (
    mathnasium_find_student,
    mathnasium_find_guardian,
    mathnasium_find_center,
    mathnasium_get_group_context,
)

G = "grp_01HA9WW1JPRN80YE0DS6ZJJN88"
C = G + "/com_01HA9X5WDX1773G0VYMJDXAVFY"
L = C + "/loc_01HA9X727AF5HY70WX56TK487M"
S = C + "/stu_01HAA03MNZRQDBMZPBDHK46CFB"
U = C + "/cust_01HMQT4DBEQF563WCQ87J7W85R"
V = L + "/srv_01HA9YHZMBYJSKJZWSYCNN8JQW"
E = C + "/emp_01HA9YC819BEJDGFG3RCK8HX9F"
A = L + "/apt_01JS5HKP34ABBTK10G4XQDQNFH"
B = G + "/com_01HZETWA0M1A669V77GQHWBT8K"
BL = B + "/loc_01HZEVJXGN4T0M56NS03AYBFVX"
BS = B + "/stu_01JQXDKRDK5QVWE7CSRQ94RCBJ"
BU = B + "/cust_01JQXDK5C9N66BJFF4CHHJX6EN"
BV = BL + "/srv_01HZEZ7RCM0C5QXY1YEHXPNR4Y"
BE = BS + "/enr_01JQXDKRRSTZYMS9RM3789W1JB"


async def run_cases():
    results = []
    cases = [
        ("booking_rules", dict(parentId=L)),
        (
            "booking_rules_service",
            dict(entityType="booking_rules", parentId=L, serviceId=V),
        ),
        ("portal_settings", dict(parentId=L)),
        ("availability_rules", dict(parentId=L, limit=1)),
        (
            "availability_window",
            dict(
                parentId=L,
                startFrom="2026-11-12T00:00:00Z",
                startTo="2026-11-13T00:00:00Z",
                limit=2,
            ),
        ),
        (
            "bookable_slots",
            dict(
                parentId=BL,
                studentId=BS,
                enrollmentId=BE,
                serviceId=BV,
                durationSeconds=1800,
                startFrom="2026-11-12T00:00:00Z",
                startTo="2026-11-13T00:00:00Z",
                limit=2,
            ),
        ),
        (
            "bookable_durations",
            dict(
                parentId=L,
                studentId=S,
                serviceId=V,
                startFrom="2026-11-12T00:00:00Z",
                startTo="2026-11-13T00:00:00Z",
            ),
        ),
        ("enrollment_balance", dict(companyId=B, studentId=BS, guardianId=BU)),
        ("recurring_series", dict(parentId=L, entityId=A)),
        ("attendance_statuses", dict(parentId=L)),
        ("guardian_profile", dict(companyId=C, entityId=U)),
        ("student_audit", dict(companyId=C, entityId=S)),
        ("record_metadata", dict(companyId=C, locationId=L)),
        ("instructor_services", dict(parentId=L, instructorId=E, limit=1)),
        ("consumer_appointment_count", dict(parentId=L, studentId=S)),
        ("radius_student", dict(entityId="R07b5WxnXlXgeEo")),
        (
            "activity_logs",
            dict(
                parentId=L,
                startFrom="2023-09-01T00:00:00Z",
                startTo="2023-10-01T00:00:00Z",
                eventIds=["ale_223", "ale_224"],
                limit=1,
            ),
        ),
        ("employees", dict(parentId=C, limit=1)),
        ("services", dict(parentId=L, limit=1)),
        ("company_settings", dict(companyId=C.split("/")[-1])),
        (
            "location_settings",
            dict(companyId=C.split("/")[-1], locationId=L.split("/")[-1]),
        ),
        ("apps", dict(companyId=C.split("/")[-1])),
        ("resources", dict(parentId=L, limit=1)),
    ]
    for label, args in cases:
        try:
            args = {"entityType": label, **args}
            r = await read(**args)
            print(label, r.get("status"), str(r.get("error", ""))[:160], flush=True)
            results.append({"label": label, "response": r})
            if r.get("next_cursor"):
                p = await read(**{**args, "cursor": r["next_cursor"]})
                print(
                    label + "_page2",
                    p.get("status"),
                    str(p.get("error", ""))[:160],
                    flush=True,
                )
                results.append({"label": label + "_page2", "response": p})
        except Exception as e:
            raise RuntimeError(f"Live QA case {label} failed") from e
    for label, fn, args in [
        (
            "appointments",
            apps,
            dict(
                student_id=S,
                customer_id=U,
                location_id=L,
                start_from="2026-08-01T00:00:00Z",
                start_to="2026-10-01T00:00:00Z",
                page_size=1,
            ),
        ),
        ("student", mathnasium_find_student, dict(studentName="Student#A-2", limit=2)),
        ("guardian", mathnasium_find_guardian, dict(parentId=C, name="Rose", limit=2)),
        (
            "center",
            mathnasium_find_center,
            dict(query="POD#A-Location-M1-B", includeInactive=True, limit=2),
        ),
        ("context", mathnasium_get_group_context, {}),
    ]:
        try:
            r = await fn(**args)
            print(
                label,
                r.get("status", "lookup"),
                str(r.get("warnings", r.get("error", "")))[:200],
                flush=True,
            )
            results.append({"label": label, "response": r})
            if r.get("next_cursor"):
                p = await fn(**{**args, "cursor": r["next_cursor"]})
                print(label + "_page2", p.get("status"), flush=True)
                results.append({"label": label + "_page2", "response": p})
        except Exception as e:
            raise RuntimeError(f"Live QA case {label} failed") from e
    Path("/private/tmp/math-live-results.json").write_text(
        json.dumps(results, indent=2)
    )


async def transport_main():
    log = open("/private/tmp/math-http-server.log", "w")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "appointy_mathnasium_mcp.server",
            "--transport",
            "streamable-http",
            "--host",
            "127.0.0.1",
            "--port",
            "8137",
            "--json-response",
        ],
        stdout=log,
        stderr=log,
    )
    try:
        async with httpx.AsyncClient() as http:
            for _ in range(50):
                try:
                    r = await http.get("http://127.0.0.1:8137/health")
                    r.raise_for_status()
                    print("HEALTH", r.status_code)
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.2)
            else:
                raise RuntimeError("Server did not become healthy")
        async with streamablehttp_client("http://127.0.0.1:8137/mcp") as streams:
            async with ClientSession(streams[0], streams[1]) as session:
                await session.initialize()
                tools = await session.list_tools()
                print("TOOLS", len(tools.tools), [t.name for t in tools.tools])

                def call(name):
                    async def invoke(**args):
                        result = await session.call_tool(name, args)
                        if result.isError:
                            raise RuntimeError(str(result.content))
                        if result.structuredContent:
                            d = result.structuredContent
                            return d.get("result", d)
                        d = json.loads(
                            next(c.text for c in result.content if c.type == "text")
                        )
                        return d.get("result", d)

                    return invoke

                suite.read = call("mathnasium_get_entity")
                suite.apps = call("mathnasium_find_appointments")
                suite.mathnasium_find_student = call("mathnasium_find_student")
                suite.mathnasium_find_guardian = call("mathnasium_find_guardian")
                suite.mathnasium_find_center = call("mathnasium_find_center")
                suite.mathnasium_get_group_context = call(
                    "mathnasium_get_group_context"
                )
                await run_cases()
                cases = json.load(open("/private/tmp/math-live-results.json"))
                for x in cases:
                    d = x["response"]
                    assert d.get("status", "success") == "success", (
                        x["label"],
                        d.get("error"),
                    )
                by_label = {c["label"]: c["response"] for c in cases}
                for kind in ["employees", "services", "appointments"]:
                    first = by_label[kind].get(
                        "items", by_label[kind].get("appointments", [])
                    )
                    second = by_label[kind + "_page2"].get(
                        "items", by_label[kind + "_page2"].get("appointments", [])
                    )
                    assert first and second and first[0]["id"] != second[0]["id"], kind
                for kind in ["guardian", "student", "center"]:
                    assert by_label[kind].get("matches"), kind
                for name, args in [
                    ("mathnasium_find_appointments", {"location_id": suite.L}),
                    (
                        "mathnasium_get_entity",
                        {"entityType": "bookable_slots", "parentId": suite.L},
                    ),
                    (
                        "mathnasium_get_entity",
                        {
                            "entityType": "company_settings",
                            "companyId": "grp_foreign/com_1",
                        },
                    ),
                    ("mathnasium_search_custom_logs", {"source": "all"}),
                ]:
                    r = await call(name)(**args)
                    assert r.get("status") == "failed", (name, r)
                    print("NEGATIVE_PASS", name)
                # Test a known center result rather than expecting an arbitrary QA name to exist.
                c = await suite.mathnasium_find_center(
                    query="POD#A-Location-M1-B", includeInactive=True, limit=1
                )
                assert c.get("matches")
                print("CENTER_EXACT_PASS")
                # Logs: check application error handling under the currently available ADC identity.
                r = await call("mathnasium_search_custom_logs")(
                    source="radius_wrappers",
                    identifiers=["test-no-such-guardian-verified-mcp"],
                    startTime="2026-11-11T00:00:00Z",
                    endTime="2026-11-11T01:00:00Z",
                    limit=1,
                    includePayload=False,
                )
                print("GCP_LIVE", r.get("status"), str(r.get("error", ""))[:120])
                print(
                    "APPOINTY_HTTP_E2E_PASS",
                    len(cases),
                    "live tool calls plus negative cases; GCP status reported separately",
                )
    finally:
        server.terminate()
        server.wait(timeout=10)
        log.close()


if __name__ == "__main__":
    if (
        os.environ.get("APPOINTY_API_BASE_URL", "").rstrip("/")
        != "https://qa-mathnasium-admin.appointy.com"
    ):
        raise SystemExit(
            "This fixture harness is QA-only. Set the QA base URL explicitly."
        )
    asyncio.run(transport_main())
