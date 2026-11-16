"""Screen -> parent map for consistent bot back-navigation."""

PARENT = {
    "buy": "main_menu",
    "my_sub": "main_menu",
    "connections": "main_menu",
    "support": "main_menu",
    "referral": "main_menu",
    "settings": "main_menu",
    "wallet": "main_menu",
    "topup": "wallet",
    "wallet_history": "wallet",
    "country": "connections",
    "orders": "my_sub",
    "free_config": "main_menu",
    "guides": "my_sub",
    "plans": "buy",
    "payment": "buy",
}


def parent_of(screen: str) -> str:
    return PARENT.get(screen, "main_menu")
