"""Reject optimistic integration readiness and leaked backend errors."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OWNER_BACKEND = ROOT / "backend/platform-owner-data/index.ts"
OWNER_AI_BACKEND = ROOT / "backend/owner-ai/index.ts"
CHECKOUT_BACKEND = ROOT / "backend/create-checkout/index.ts"
STRIPE_WEBHOOK_BACKEND = ROOT / "backend/stripe-webhook/index.ts"
SALES_INQUIRY_BACKEND = ROOT / "backend/sales-inquiry/index.ts"
SEND_SMS_BACKEND = ROOT / "backend/send-sms/index.ts"


def scan(source: str) -> list[str]:
    failures: list[str] = []
    optimistic = re.compile(
        r"\b(?:const|let)\s+[A-Za-z0-9_]*(?:sender|secret|key|token|connected|present)"
        r"[A-Za-z0-9_]*\s*=\s*true\b",
        re.IGNORECASE,
    )
    if optimistic.search(source):
        failures.append("integration evidence must not be hard-coded to true")
    if re.search(r"return\s+json\s*\(\s*\{\s*error\s*:\s*[^}]*\.message", source):
        failures.append("internal exception messages must not be returned to clients")
    if 'console.error("platform-owner-data",e)' not in source:
        failures.append("owner backend must keep a server-side error log")
    if 'error:"Správu platformy nyní nelze načíst."' not in source:
        failures.append("owner backend must return the approved generic error")
    if 'if(!url||!pub||!secret)return json({error:"Server configuration missing"},500);' not in source:
        failures.append("server configuration errors must exclude request authentication")
    if 'if(!auth?.startsWith("Bearer "))return json({error:"Not authenticated"},401);' not in source:
        failures.append("missing or malformed bearer authentication must return 401")
    required_volai_gate = (
        'ready:volaiIntegration?.status==="connected"&&volaiApiKeyPresent&&'
        'volaiWebhookSecretPresent&&volaiSenderPresent&&activeVolaiRoutes.length>0'
    )
    if required_volai_gate not in source:
        failures.append("Volai readiness must require every connected-state signal")
    return failures


def scan_error_boundary(source: str, label: str, log_marker: str, generic_error: str) -> list[str]:
    failures: list[str] = []
    if log_marker not in source:
        failures.append(f"{label} must keep a server-side error log")
    if generic_error not in source:
        failures.append(f"{label} must return its approved generic error")
    if re.search(r"return\s+json\s*\(\s*\{\s*error\s*:\s*[^}]*\.message", source):
        failures.append(f"{label} must not return internal exception messages")
    return failures


def scan_checkout_input(source: str) -> list[str]:
    failures: list[str] = []
    membership_query = 'admin.from("organization_memberships")'
    body_limit = 'byteLength>4096)return json({error:"Požadavek je příliš dlouhý."},413)'
    malformed_body = 'return json({error:"Neplatný požadavek."},400)'
    uuid_guard = 'if(!uuidPattern.test(orgId))return json({error:"Neplatná firma."},400);'
    if body_limit not in source:
        failures.append("checkout request bodies must be capped before privileged queries")
    if malformed_body not in source or "JSON.parse(rawBody)" not in source:
        failures.append("malformed checkout JSON must return 400")
    if uuid_guard not in source:
        failures.append("checkout organization IDs must be validated")
    if membership_query in source:
        membership_offset = source.index(membership_query)
        for guard, message in (
            (body_limit, "checkout body limit must run before membership lookup"),
            (uuid_guard, "checkout organization validation must run before membership lookup"),
        ):
            if guard in source and source.index(guard) > membership_offset:
                failures.append(message)
    return failures


def scan_owner_input(source: str) -> list[str]:
    failures: list[str] = []
    summary_branch = 'if(action==="summary")'
    body_reader = "readLimitedBody(req,MAX_OWNER_DATA_BYTES)"
    body_limit = 'if(rawBody===null)return json({error:"Požadavek je příliš dlouhý."},413)'
    malformed_body = 'return json({error:"Neplatný požadavek."},400)'
    if "const MAX_OWNER_DATA_BYTES=" not in source or body_reader not in source:
        failures.append("owner request bodies must use a fixed byte limit")
    if "value.byteLength" not in source or "reader.cancel()" not in source:
        failures.append("owner body reads must stop after the byte limit")
    if body_limit not in source:
        failures.append("oversized owner requests must return 413")
    if malformed_body not in source or "JSON.parse(rawBody)" not in source:
        failures.append("malformed owner JSON must return 400")
    if summary_branch in source:
        summary_offset = source.index(summary_branch)
        for guard, message in (
            (body_reader, "owner body read must run before summary queries"),
            (body_limit, "owner body limit must run before summary queries"),
            (malformed_body, "owner JSON validation must run before summary queries"),
        ):
            if guard in source and source.index(guard) > summary_offset:
                failures.append(message)
    return failures


def scan_owner_ai_input(source: str) -> list[str]:
    failures: list[str] = []
    handler_marker = "Deno.serve(async req=>{"
    handler = source[source.index(handler_marker):] if handler_marker in source else source
    body_reader = "readLimitedBody(req,MAX_OWNER_AI_BYTES)"
    body_rejection = 'if(raw===null)return json({error:"Požadavek je příliš dlouhý."},413)'
    auth_rejection = 'if(!auth.startsWith("Bearer "))return json({error:"Přihlaste se do aplikace."},401)'
    owner_rejection = 'if(roleError||!owner)return json({error:"Přístup pouze pro vlastníka platformy."},403)'
    malformed_body = 'return json({error:"Neplatný požadavek."},400)'
    unavailable_response = 'return json({error:"AI služba ještě není připojená.'
    if "const MAX_OWNER_AI_BYTES=" not in source or body_reader not in handler:
        failures.append("owner AI bodies must use a fixed byte limit")
    if "value.byteLength" not in source or "reader.cancel()" not in source:
        failures.append("owner AI body reads must stop after the byte limit")
    if body_rejection not in handler:
        failures.append("oversized owner AI bodies must return 413")
    if "JSON.parse(raw)" not in handler or malformed_body not in handler:
        failures.append("malformed owner AI JSON must return 400")
    if body_reader in handler:
        reader_offset = handler.index(body_reader)
        for guard, message in (
            (auth_rejection, "owner AI authentication must run before reading the body"),
            (owner_rejection, "owner AI authorization must run before reading the body"),
        ):
            if guard not in handler or handler.index(guard) > reader_offset:
                failures.append(message)
        if unavailable_response in handler and reader_offset > handler.index(unavailable_response):
            failures.append("owner AI input validation must run before provider handling")
    return failures


def scan_stripe_webhook_input(source: str) -> list[str]:
    failures: list[str] = []
    handler_marker = "Deno.serve(async(req:Request)=>{"
    handler = source[source.index(handler_marker):] if handler_marker in source else source
    body_reader = "readWebhookBody(req,MAX_WEBHOOK_BYTES)"
    body_rejection = 'if(raw===null)return new Response("payload too large",{status:413})'
    privileged_setup = "const admin=db();"
    signature_check = "if(!(await verifyStripe(raw,"
    json_parse = "JSON.parse(raw)"
    if "const MAX_WEBHOOK_BYTES=" not in source or body_reader not in handler:
        failures.append("Stripe webhook bodies must use a fixed byte limit")
    if "value.byteLength" not in source or "reader.cancel()" not in source:
        failures.append("Stripe webhook body reads must stop after the byte limit")
    if body_rejection not in handler:
        failures.append("oversized Stripe webhook bodies must return 413")
    if privileged_setup in handler and body_rejection in handler:
        if handler.index(body_rejection) > handler.index(privileged_setup):
            failures.append("Stripe webhook size rejection must run before privileged setup")
    if signature_check not in handler or json_parse not in handler:
        failures.append("Stripe webhook signatures must be checked before JSON parsing")
    elif handler.index(signature_check) > handler.index(json_parse):
        failures.append("Stripe webhook signatures must be checked before JSON parsing")
    return failures


def scan_sales_inquiry_input(source: str) -> list[str]:
    failures: list[str] = []
    handler_marker = "Deno.serve(async req=>{"
    handler = source[source.index(handler_marker):] if handler_marker in source else source
    body_reader = "readLimitedBody(req,MAX_INQUIRY_BYTES)"
    body_rejection = "if(raw===null||raw.length>6000)return json"
    privileged_setup = "const admin=createClient("
    if "const MAX_INQUIRY_BYTES=" not in source or body_reader not in handler:
        failures.append("sales inquiry bodies must use a fixed byte limit")
    if "value.byteLength" not in source or "reader.cancel()" not in source:
        failures.append("sales inquiry body reads must stop after the byte limit")
    if body_rejection not in handler or "413" not in handler:
        failures.append("oversized sales inquiries must return 413")
    if privileged_setup in handler and body_rejection in handler:
        if handler.index(body_rejection) > handler.index(privileged_setup):
            failures.append("sales inquiry size rejection must run before privileged setup")
    return failures


def scan_send_sms_input(source: str) -> list[str]:
    failures: list[str] = []
    body_reader = "readLimitedBody(req,MAX_SMS_BYTES)"
    body_rejection = 'if(raw===null)return json({error:"Požadavek je příliš dlouhý."},413)'
    malformed_body = 'return json({error:"Neplatný požadavek."},400)'
    org_guard = 'if(!uuidPattern.test(organizationId))return json({error:"Neplatná firma."},400)'
    membership_scope = '.eq("user_id",user.id).eq("organization_id",organizationId)'
    integration_scope = '.eq("organization_id",organizationId).eq("provider","volai")'
    provider_call = 'fetch("https://volai.cz/v1/messages"'
    connected_gate = 'integration?.status!=="connected"||!apiKey'
    if "const MAX_SMS_BYTES=" not in source or body_reader not in source:
        failures.append("SMS request bodies must use a fixed byte limit")
    if "value.byteLength" not in source or "reader.cancel()" not in source:
        failures.append("SMS body reads must stop after the byte limit")
    if body_rejection not in source:
        failures.append("oversized SMS requests must return 413")
    if "JSON.parse(raw)" not in source or malformed_body not in source:
        failures.append("malformed SMS JSON must return 400")
    if org_guard not in source:
        failures.append("SMS organization IDs must be validated")
    if membership_scope not in source:
        failures.append("SMS membership lookup must target the requested organization")
    if integration_scope not in source:
        failures.append("SMS integration lookup must target the requested organization")
    if provider_call in source:
        provider_offset = source.index(provider_call)
        for guard, message in (
            (body_rejection, "SMS body limit must run before the provider call"),
            (org_guard, "SMS organization validation must run before the provider call"),
            (membership_scope, "SMS membership check must run before the provider call"),
            (integration_scope, "SMS integration check must run before the provider call"),
            (connected_gate, "SMS connected-state gate must run before the provider call"),
        ):
            if guard not in source or source.index(guard) > provider_offset:
                failures.append(message)
    return failures


def main() -> int:
    try:
        source = OWNER_BACKEND.read_text(encoding="utf-8")
        owner_ai_source = OWNER_AI_BACKEND.read_text(encoding="utf-8")
        checkout_source = CHECKOUT_BACKEND.read_text(encoding="utf-8")
        stripe_webhook_source = STRIPE_WEBHOOK_BACKEND.read_text(encoding="utf-8")
        sales_inquiry_source = SALES_INQUIRY_BACKEND.read_text(encoding="utf-8")
        send_sms_source = SEND_SMS_BACKEND.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"FAIL: cannot read {OWNER_BACKEND.relative_to(ROOT)}: {error}")
        return 1
    failures = scan(source)
    failures.extend(scan_owner_input(source))
    failures.extend(scan_error_boundary(
        owner_ai_source,
        "owner AI backend",
        'console.error("owner-ai",e)',
        'error:"AI služba není dostupná."',
    ))
    failures.extend(scan_owner_ai_input(owner_ai_source))
    failures.extend(scan_error_boundary(
        checkout_source,
        "checkout backend",
        'console.error("create-checkout",e)',
        'error:"Platbu nyní nelze připravit."',
    ))
    failures.extend(scan_checkout_input(checkout_source))
    failures.extend(scan_stripe_webhook_input(stripe_webhook_source))
    failures.extend(scan_sales_inquiry_input(sales_inquiry_source))
    failures.extend(scan_error_boundary(
        send_sms_source,
        "SMS backend",
        'console.error("send-sms",error)',
        'error:"SMS nyní nelze odeslat."',
    ))
    failures.extend(scan_send_sms_input(send_sms_source))
    for failure in failures:
        print("FAIL:", failure)
    print(f"Privileged backend readiness checked; {len(failures)} failures.")
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
