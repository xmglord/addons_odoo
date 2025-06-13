{
    "name": "Telegram Bot",
    "version": "1.0",
    "category": "Technical",
    "summary": "Module to use telegram bot for Odoo processes.",
    "license": "OPL-1",
    "author": "German Loredo Becerra",
    "depends": [
        "base",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/telegram_bot_views.xml",
        "views/telegram_login_request_views.xml",
    ],
    "installable": True,
    "application": True,
}
