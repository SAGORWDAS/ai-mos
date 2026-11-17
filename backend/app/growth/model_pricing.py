"""Conservative text reservations and provider-side advertised-price ceilings."""

from decimal import ROUND_CEILING, Decimal, InvalidOperation


def request_pricing(snapshot, operation, instruction, system_prompt, max_output_tokens=1800):
    rates = snapshot.get("pricing", {}).get("rates", {})
    try:
        request = Decimal(str(rates.get("request", "0")))
        if operation == "image":
            # A lower advertised fee is not a complete resolution/tier quote.
            if not any(name in rates for name in ("image", "request")):
                return None, None
            amount = Decimal(str(rates.get("image", "0"))) + request
            if not amount.is_finite() or amount < 0:
                raise ValueError()
            return int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING)), None
        prompt = Decimal(str(rates["prompt"]))
        texts = instruction if isinstance(instruction, list) else [instruction]
        # UTF-8 bytes are deliberately more conservative than a chars/4 token estimate.
        input_bound = sum(len(text.encode()) for text in texts) + 256
        if operation == "chat":
            input_bound += len(system_prompt.encode())
            completion = Decimal(str(rates["completion"]))
            amount = prompt * input_bound + completion * max_output_tokens + request
            routing = {
                "sort": "price",
                "max_price": {
                    "prompt": float(prompt * 1000000),
                    "completion": float(completion * 1000000),
                    "request": float(request),
                },
            }
        else:
            amount, routing = prompt * input_bound + request, None
        if not amount.is_finite() or amount < 0:
            raise ValueError()
        return int((amount * 1000000).to_integral_value(rounding=ROUND_CEILING)), routing
    except (KeyError, ValueError, TypeError, InvalidOperation):
        return None, None
