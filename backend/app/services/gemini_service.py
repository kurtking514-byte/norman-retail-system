
"""
Gemini AI-powered response generation for Messenger conversations.

Provides two main functions:

- :func:`build_shop_context` — queries the database and assembles a compact
  text block that grounds the LLM on real product/FAQ/promotion data.
- :func:`generate_reply` — takes a customer message and conversation history,
  calls the Gemini API with tool-calling (function-calling) support, and
  returns an :class:`AIReplyResult` with the generated reply and handoff-
  detection flags.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.business import FAQ, Promotion
from app.models.product import Product

# Use the modern google.genai package (the old google.generativeai is deprecated).
try:
    from google.genai import Client
    from google.genai import types as genai_types
except ImportError:
    Client = None  # type: ignore[assignment, misc]
    genai_types = None  # type: ignore[assignment]

from app.schemas.ai_response import AIReplyResult

# Import tool functions
from app.services.ai_tools_service import (
    check_product_availability,
    check_repair_status,
    create_reservation_via_chat,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Keywords that signal a customer wants a refund, is complaining, or is
# frustrated enough that a human should handle the conversation.
HANDOFF_KEYWORDS = {
    "refund",
    "complaint",
    "manager",
    "terrible",
    "scam",
    "horrible",
    "worst",
    "useless",
    "broken",
    "defective",
    "lawyer",
    "attorney",
    "lawsuit",
    "damages",
    "overcharge",
}

# Phrases that ask about features not yet implemented (Phase 6/7).
# If the message contains these, we cannot answer from the shop context alone.
UNSUPPORTED_TOPIC_PHRASES = [
    "repair status",
    "repair update",
    "my repair",
    "my reservation",
    "reservation status",
    "change reservation",
    "cancel reservation",
    "when will my",
    "pickup date",
    "ready for pickup",
    "schedule repair",
    "appointment",
]

# Maximum number of tool-calling round-trips per customer message.
MAX_TOOL_ROUNDTRIPS = 3

# ---------------------------------------------------------------------------
# Tool definitions (lazy-initialized)
# ---------------------------------------------------------------------------

_TOOL_DEFINITIONS = None


def _get_tool_definitions() -> list:
    """Build Gemini SDK tool declarations for our AI tools."""
    global _TOOL_DEFINITIONS
    if _TOOL_DEFINITIONS is not None:
        return _TOOL_DEFINITIONS

    if genai_types is None:
        _TOOL_DEFINITIONS = []
        return _TOOL_DEFINITIONS

    _TOOL_DEFINITIONS = [
        genai_types.Tool(function_declarations=[
            genai_types.FunctionDeclaration(
                name="check_product_availability",
                description=(
                    "Check real-time stock availability for a product. Use this "
                    "when a customer asks if a product is in stock, how many are "
                    "available, or what the selling price is."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    required=["product_name_or_model"],
                    properties={
                        "product_name_or_model": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Full or partial product name or model number",
                        ),
                    },
                ),
            ),
            genai_types.FunctionDeclaration(
                name="create_reservation_via_chat",
                description=(
                    "Reserve/hold a product for a customer who has explicitly "
                    "asked to reserve it. ONLY use when customer clearly states "
                    "they want to reserve/hold an item — NOT just asking about it."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    required=["messenger_user_id", "product_name_or_model"],
                    properties={
                        "messenger_user_id": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="The customer's Messenger sender ID",
                        ),
                        "product_name_or_model": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Product name or model to reserve",
                        ),
                    },
                ),
            ),
            genai_types.FunctionDeclaration(
                name="check_repair_status",
                description=(
                    "Look up the status of a customer's most recent repair request. "
                    "Use when customer asks about repair status or when device will be ready."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    required=["messenger_user_id"],
                    properties={
                        "messenger_user_id": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="The customer's Messenger sender ID",
                        ),
                    },
                ),
            ),
        ]),
    ]
    return _TOOL_DEFINITIONS


# Tool execution registry
_TOOL_FUNCTIONS = {
    "check_product_availability": check_product_availability,
    "create_reservation_via_chat": create_reservation_via_chat,
    "check_repair_status": check_repair_status,
}

# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


async def build_shop_context(db: AsyncSession) -> str:
    """Query the database and return a compact text block for Gemini grounding.

    Includes:
    - Up to 30 active products (name, model_number, selling_price, description).
      **Never includes cost_price.**
    - All FAQ question/answer pairs.
    - Active promotions whose date range includes today.

    Returns a plaintext string ready to be injected into the system prompt.
    """
    lines: list[str] = []
    lines.append("=== NORMAN CELLPHONE CENTER AND REPAIR SHOP — SHOP DATA ===")
    lines.append("")

    # ---- Products (active, max 30) -------------------------------------------
    result = await db.execute(
        select(Product)
        .where(Product.is_active.is_(True))
        .limit(30)
    )
    products = result.scalars().all()

    if products:
        lines.append("--- PRODUCTS ---")
        for p in products:
            desc = (p.description or "").strip()
            desc_line = f" — {desc}" if desc else ""
            # IMPORTANT: only selling_price, never cost_price
            lines.append(
                f"  • {p.name} (Model: {p.model_number}) — "
                f"₱{p.selling_price:.2f}{desc_line}"
            )
        lines.append("")

    # ---- FAQs ----------------------------------------------------------------
    result = await db.execute(select(FAQ))
    faqs = result.scalars().all()

    if faqs:
        lines.append("--- FREQUENTLY ASKED QUESTIONS ---")
        for faq in faqs:
            lines.append(f"  Q: {faq.question}")
            lines.append(f"  A: {faq.answer}")
        lines.append("")

    # ---- Promotions (active and within date range) ---------------------------
    now = datetime.now()
    result = await db.execute(
        select(Promotion).where(Promotion.active.is_(True))
    )
    all_active = result.scalars().all()

    active_promos = []
    for promo in all_active:
        if promo.start_date and promo.start_date > now:
            continue
        if promo.end_date and promo.end_date < now:
            continue
        active_promos.append(promo)

    if active_promos:
        lines.append("--- ACTIVE PROMOTIONS ---")
        for promo in active_promos:
            date_range = ""
            if promo.start_date and promo.end_date:
                date_range = (
                    f" ({promo.start_date.strftime('%b %d')} – "
                    f"{promo.end_date.strftime('%b %d, %Y')})"
                )
            elif promo.start_date:
                date_range = f" (from {promo.start_date.strftime('%b %d, %Y')})"
            elif promo.end_date:
                date_range = f" (until {promo.end_date.strftime('%b %d, %Y')})"

            desc = (promo.description or "").strip()
            desc_line = f" — {desc}" if desc else ""
            lines.append(f"  • {promo.title}{date_range}{desc_line}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handoff detection helpers
# ---------------------------------------------------------------------------


def _check_keyword_handoff(message_lower: str) -> str | None:
    """Return a handoff reason if the message contains complaint keywords."""
    for kw in HANDOFF_KEYWORDS:
        if kw in message_lower:
            return f"Customer message contains handoff keyword: '{kw}'"
    return None


def _check_unsupported_topic(message_lower: str) -> str | None:
    """Return a handoff reason if the message mentions an unsupported topic."""
    for phrase in UNSUPPORTED_TOPIC_PHRASES:
        if phrase in message_lower:
            return f"Customer asked about unsupported topic: '{phrase}'"
    return None


# ---------------------------------------------------------------------------
# Main reply generator
# ---------------------------------------------------------------------------

HOLDING_MESSAGE = (
    "Thanks for reaching out! Let me get one of our team members to help "
    "with that — they'll be with you shortly."
)

FALLBACK_MESSAGE = (
    "Thanks for your message! We've received it and one of our team "
    "members will get back to you as soon as possible."
)

_SYSTEM_PROMPT_TEMPLATE = """\
You are a helpful customer-service assistant for "Norman Cellphone Center And Repair Shop," a cellphone and gadget repair and retail shop in the Philippines.

**Rules:**
1. Answer ONLY using the shop context provided below. Never invent prices, specifications, or products that are not present in the context.
2. Keep replies concise and friendly — this is a Messenger chat, not an essay. 1-3 short paragraphs is ideal.
3. If the customer asks about something NOT covered in the context (e.g. repair status lookups, reservation changes), you may politely say you don't have that information yet.
4. If you are NOT confident that you can answer correctly based on the context provided, begin your response with the literal marker: [UNCERTAIN] followed by your best-effort answer. Example: "[UNCERTAIN] I'm not sure I have enough information to answer that correctly. Could you ask about our products or services?"
5. If you can answer confidently, just provide the answer without any prefix.

**IMPORTANT:**
- NEVER reveal cost_price or wholesale pricing.
- NEVER promise things not in the context.
- Be polite and professional at all times.

**Available Tools:**
You have access to three tools that can query live data or take actions:
1. **check_product_availability** — Use this when a customer asks about stock, price, or availability. Queries live database.
2. **create_reservation_via_chat** — Use this ONLY when a customer explicitly asks to reserve/hold a specific item (not just asking about it).
3. **check_repair_status** — Use this when a customer asks about their repair status or when their device will be ready.

When a customer asks about something that requires a tool call, call the appropriate tool and wait for the result before forming your response.

=== SHOP CONTEXT ===
{context}
=== END CONTEXT ===

Now respond to the customer's latest message, keeping the conversation history in mind.
"""


async def generate_reply(
    db: AsyncSession,
    customer_message: str,
    conversation_history: list[dict],
) -> AIReplyResult:
    """Generate a context-aware reply using Gemini API with tool calling.

    Parameters
    ----------
    db:
        Database session for querying shop context and executing tool calls.
    customer_message:
        The latest message from the customer.
    conversation_history:
        Recent conversation history as a list of dicts with keys
        ``speaker`` (``"User"`` or ``"Bot"``) and ``text``.  Typically
        the last ~6 messages.

    Returns
    -------
    AIReplyResult
        The reply text and handoff flags.
    """
    # ===== DEBUG: Log entry into generate_reply =====
    logger.info("DEBUG generate_reply — ENTERED, message=%s, history_len=%s",
                 customer_message, len(conversation_history))
    # ================================================

    # ---- Step 1: Pre-handoff checks -----------------------------------------
    message_lower = customer_message.lower().strip()

    reason = _check_keyword_handoff(message_lower)
    if reason is None:
        reason = _check_unsupported_topic(message_lower)

    if reason is not None:
        logger.info("DEBUG generate_reply — RETURNING handoff at STEP 1 (pre-handoff check), reason=%s", reason)
        return AIReplyResult(
            reply_text=HOLDING_MESSAGE,
            needs_human_handoff=True,
            handoff_reason=reason,
        )

    logger.info("DEBUG generate_reply — PASSED step 1 (no keyword/unsupported handoff)")

    # ---- Step 2: Build context and system prompt -----------------------------
    try:
        context = await build_shop_context(db)
        logger.info("DEBUG generate_reply — context built, length=%s chars", len(context))
    except Exception as exc:
        logger.exception("Failed to build shop context: %s", exc)
        logger.info("DEBUG generate_reply — RETURNING fallback at STEP 2 (build_shop_context exception)")
        return AIReplyResult(
            reply_text=FALLBACK_MESSAGE,
            needs_human_handoff=True,
            handoff_reason="Error building shop context",
        )

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(context=context)

    # ---- Step 3: Build conversation history as Content objects ---------------
    contents: list = []
    contents.append(genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=system_prompt)],
    ))
    for msg in conversation_history[-6:]:
        role = "user" if msg["speaker"] == "User" else "model"
        contents.append(genai_types.Content(
            role=role,
            parts=[genai_types.Part(text=msg["text"])],
        ))

    logger.info("DEBUG generate_reply — PASSED step 3, about to call _call_gemini_v2 (step 4)")

    # ---- Step 4: Call Gemini API with tools ----------------------------------
    try:
        reply_text = await _call_gemini_v2(
            db=db,
            contents=contents,
            user_message=customer_message,
            conversation_history=conversation_history,
        )
        logger.info("DEBUG generate_reply — _call_gemini_v2 returned OK, reply_text[:80]=%s", reply_text[:80] if reply_text else "None")
    except Exception as exc:
        logger.exception("Gemini API call with tools failed: %s", exc)
        logger.info("DEBUG generate_reply — RETURNING fallback at STEP 4 (Gemini API exception)")
        return AIReplyResult(
            reply_text=FALLBACK_MESSAGE,
            needs_human_handoff=True,
            handoff_reason=f"Gemini API error: {exc}",
        )

    # ---- Step 5: Check for uncertainty marker --------------------------------
    if reply_text.startswith("[UNCERTAIN]"):
        logger.info("DEBUG generate_reply — RETURNING handoff at STEP 5 (uncertainty marker)")
        return AIReplyResult(
            reply_text=HOLDING_MESSAGE,
            needs_human_handoff=True,
            handoff_reason="Gemini indicated uncertainty about the answer",
        )

    # ---- Step 6: Normal reply ------------------------------------------------
    logger.info("DEBUG generate_reply — RETURNING normal reply at STEP 6")
    return AIReplyResult(
        reply_text=reply_text,
        needs_human_handoff=False,
        handoff_reason=None,
    )


# ---------------------------------------------------------------------------
# Guardrail: product name confirmation for create_reservation_via_chat
# ---------------------------------------------------------------------------


def _product_name_in_conversation(
    product_name: str,
    customer_message: str,
    conversation_history: list[dict],
) -> bool:
    """Check if *product_name* appears in current message or last 2 turns.

    Lightweight sanity check to reduce chance of Gemini reserving the
    wrong product due to misunderstanding.
    """
    check_texts = [customer_message]
    for msg in conversation_history[-2:]:
        check_texts.append(msg.get("text", ""))

    product_lower = product_name.lower()
    for text in check_texts:
        if product_lower in text.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Gemini API call with tool-calling loop
# ---------------------------------------------------------------------------


async def _call_gemini_v2(
    db: AsyncSession,
    contents: list,
    user_message: str,
    conversation_history: list[dict],
) -> str:
    """Call Gemini with tool declarations and handle the tool-calling loop.

    Up to ``MAX_TOOL_ROUNDTRIPS`` (3) round-trips are allowed.
    """
    logger.info("DEBUG _call_gemini_v2 — ENTERED, user_message=%s", user_message)

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.error("DEBUG _call_gemini_v2 — GEMINI_API_KEY is empty, raising")
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it in .env or environment "
            "variables before making Gemini API calls."
        )
    if Client is None or genai_types is None:
        raise RuntimeError(
            "google.genai package is not installed. "
            "Run: pip install google-generativeai"
        )

    client = Client(api_key=api_key)

    # Append the user's latest message
    full_contents = list(contents)
    full_contents.append(genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=user_message)],
    ))

    tools = _get_tool_definitions()

    for round_num in range(MAX_TOOL_ROUNDTRIPS + 1):
        config = genai_types.GenerateContentConfig(
            tools=tools,
            temperature=0.7,
        )

        # DEBUG: Log masked API key to verify which key is being used
        masked_key = api_key[:10] + "..." if len(api_key) > 10 else "(empty)"
        logger.info("DEBUG gemini_call_v2 — API key start: %s, model=gemini-2.5-flash, round=%s, tools=%s",
                     masked_key, round_num, bool(tools))
        logger.debug("DEBUG gemini_call_v2 — full contents count: %s", len(full_contents))

        try:
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_contents,
                config=config,
            )
        except Exception as exc:
            logger.exception("DEBUG gemini_call_v2 — API call FAILED with exception:")
            logger.error("DEBUG gemini_call_v2 — Exception type: %s, args: %s", type(exc).__name__, exc.args)
            raise

        function_calls = response.function_calls
        if not function_calls:
            logger.info("DEBUG _call_gemini_v2 — RETURNING response.text at round=%s, response text[:80]=%s",
                         round_num, response.text[:80] if response.text else "None")
            return response.text

        if round_num >= MAX_TOOL_ROUNDTRIPS:
            logger.info("DEBUG _call_gemini_v2 — RETURNING HOLDING_MESSAGE at round=%s (max roundtrips reached)", round_num)
            return HOLDING_MESSAGE

        tool_parts: list = []
        for fc in function_calls:
            func_name = fc.name
            func_args = fc.args or {}

            # Guardrail: only execute create_reservation if product mentioned
            if func_name == "create_reservation_via_chat":
                product_arg = func_args.get("product_name_or_model", "")
                if product_arg and not _product_name_in_conversation(
                    product_arg, user_message, conversation_history
                ):
                    tool_parts.append(genai_types.Part(
                        function_response=genai_types.FunctionResponse(
                            id=fc.id,
                            name=func_name,
                            response={
                                "success": False,
                                "reason": (
                                    f"I'm not sure which product you mean by "
                                    f"'{product_arg}'. Could you please confirm "
                                    f"the exact product name you'd like to reserve?"
                                ),
                            },
                        ),
                    ))
                    continue

            func = _TOOL_FUNCTIONS.get(func_name)
            if func is None:
                result_dict = {"error": f"Unknown tool: {func_name}"}
            else:
                try:
                    result_dict = await func(db, **func_args)
                except Exception as exc:
                    logger.exception("Tool %s failed: %s", func_name, exc)
                    result_dict = {
                        "success": False,
                        "reason": f"An error occurred while running {func_name}.",
                    }

            result_dict = dict(result_dict)
            tool_parts.append(genai_types.Part(
                function_response=genai_types.FunctionResponse(
                    id=fc.id,
                    name=func_name,
                    response=result_dict,
                ),
            ))

        full_contents.append(genai_types.Content(
            role="model",
            parts=[genai_types.Part(function_call=fc) for fc in function_calls],
        ))
        full_contents.append(genai_types.Content(
            role="user",
            parts=tool_parts,
        ))

    logger.info("DEBUG _call_gemini_v2 — RETURNING HOLDING_MESSAGE at end of function (max roundtrips reached)")
    return HOLDING_MESSAGE


# ---------------------------------------------------------------------------
# Gemini API call (wrapped for testability)
# ---------------------------------------------------------------------------


async def _call_gemini(prompt: str) -> str:
    """Send *prompt* to the Gemini API and return the response text.

    Raises on network errors, rate limits, auth failures, etc. — the caller
    is responsible for catching and converting to a safe fallback.

    Uses the ``google.genai`` package (``gemini-2.5-flash`` model).
    """
    api_key = settings.GEMINI_API_KEY

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Set it in .env or environment "
            "variables before making Gemini API calls."
        )

    if Client is None:
        raise RuntimeError(
            "google.genai package is not installed. "
            "Run: pip install google-generativeai"
        )

    client = Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text
