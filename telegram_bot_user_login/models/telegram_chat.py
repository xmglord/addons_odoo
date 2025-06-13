from odoo import api, fields, models


class TelegramChat(models.Model):
    _name = "telegram.chat"
    _description = "Telegram Chat Session"

    chat_id = fields.Char(string="Chat ID", required=True, index=True, readonly=True)
    bot_id = fields.Many2one("telegram.bot", string="Bot", required=True, readonly=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", string="Odoo User", readonly=True)

    _sql_constraints = [("chat_id_bot_id_uniq", "unique (chat_id, bot_id)", "A chat ID must be unique per bot!")]

    @api.model
    def _find_or_create(self, chat_id, bot_id):
        """Finds an existing chat record or creates a new one."""
        chat_id_str = str(chat_id)
        chat = self.search([("chat_id", "=", chat_id_str), ("bot_id", "=", bot_id)], limit=1)
        if not chat:
            chat = self.create({"chat_id": chat_id_str, "bot_id": bot_id})
        return chat
