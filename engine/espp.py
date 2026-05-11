"""ESPP (Employee Stock Purchase Plan) calculations."""


def calculate_espp_purchase(
    base_salary_annual: int,
    contribution_rate_percent: int,
    num_periods: int,
    base_price: int,
    purchase_price_with_discount: int,
) -> dict:
    """
    Calculate ESPP purchase amounts and gains.

    Args:
        base_salary_annual: Annual salary in minor units
        contribution_rate_percent: Contribution % (× 100, e.g., 1000 = 10%)
        num_periods: Number of purchase periods in offering
        base_price: Stock price at offering start (or min with lookback) in minor units
        purchase_price_with_discount: Discounted purchase price in minor units

    Returns:
        {
            'contribution_per_period': int,
            'total_contribution': int,
            'shares_purchased': int (milliShares),
            'immediate_gain': int (minor units),
        }
    """
    monthly_salary = base_salary_annual // 12
    contribution_per_period = (monthly_salary * contribution_rate_percent) // 10000
    total_contribution = contribution_per_period * num_periods

    # Shares purchased = total contribution / purchase price
    if purchase_price_with_discount == 0:
        shares_purchased_millis = 0
    else:
        shares_purchased_millis = (total_contribution * 1000) // purchase_price_with_discount

    # Immediate gain = discount amount on contributed shares
    # gain = contribution_total * (base_price - purchase_price) / base_price
    # But easier: gain = contribution_total - (shares * purchase_price)
    if purchase_price_with_discount == 0:
        immediate_gain = 0
    else:
        shares_value_at_purchase = (shares_purchased_millis * purchase_price_with_discount) // 1000
        immediate_gain = total_contribution - shares_value_at_purchase

    return {
        "contribution_per_period": contribution_per_period,
        "total_contribution": total_contribution,
        "shares_purchased": shares_purchased_millis,
        "immediate_gain": immediate_gain,
    }


def calculate_purchase_price(
    offering_start_price: int,
    purchase_date_price: int,
    discount_rate: int,
    has_lookback: bool,
) -> int:
    """
    Calculate the purchase price after discount and lookback.

    Args:
        offering_start_price: Stock price at offering start (minor units)
        purchase_date_price: Stock price at purchase date (minor units)
        discount_rate: Discount % (× 100, e.g., 1500 = 15%)
        has_lookback: If True, use min(offering_start, purchase_date); else use purchase_date

    Returns:
        Final purchase price (minor units) after discount
    """
    # Select base price
    if has_lookback:
        base_price = min(offering_start_price, purchase_date_price)
    else:
        base_price = purchase_date_price

    # Apply discount: purchase_price = base_price * (1 - discount_rate / 10000)
    purchase_price = base_price - (base_price * discount_rate // 10000)
    return purchase_price
