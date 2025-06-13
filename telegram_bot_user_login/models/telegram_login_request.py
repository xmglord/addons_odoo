import logging

from odoo import _, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class TelegramLoginRequest(models.Model):
    _name = "telegram.login.request"
    _description = "Telegram Login Request"
    _order = "create_date desc"

    chat_id = fields.Many2one(
        "telegram.chat", string="Telegram Chat", required=True, readonly=True, ondelete="cascade"
    )
    telegram_username = fields.Char(string="Telegram User", readonly=True)
    telegram_user_full_name = fields.Char(string="Telegram Full Name", readonly=True)
    requested_user_id = fields.Many2one("res.users", string="Requested Odoo User", required=True, readonly=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("approved", "Approved"),
            ("denied", "Denied"),
        ],
        string="Status",
        default="pending",
        readonly=True,
        copy=False,
    )

    processed_by_id = fields.Many2one("res.users", string="Processed By", readonly=True)
    processed_date = fields.Datetime(string="Processed Date", readonly=True)

    def action_approve(self):
        """Approves the login request."""
        for req in self:
            if req.state != "pending":
                raise ValidationError(_("This request has already been processed."))

            req.chat_id.user_id = req.requested_user_id

            req.write(
                {
                    "state": "approved",
                    "processed_by_id": self.env.user.id,
                    "processed_date": fields.Datetime.now(),
                }
            )

            success_message = f"✅ Your request to log in as *{req.requested_user_id.name}* has been approved."
            req.chat_id.bot_id.send_message(req.chat_id.chat_id, success_message)
            _logger.info(
                "Approved login request %s for Odoo user '%s' from chat %s",
                req.id,
                req.requested_user_id.name,
                req.chat_id.chat_id,
            )

    def action_deny(self):
        """Denies the login request."""
        for req in self:
            if req.state != "pending":
                raise ValidationError(_("This request has already been processed."))

            req.write(
                {
                    "state": "denied",
                    "processed_by_id": self.env.user.id,
                    "processed_date": fields.Datetime.now(),
                }
            )

            denial_message = "❌ Your request to log in has been denied by an administrator."
            req.chat_id.bot_id.send_message(req.chat_id.chat_id, denial_message)
            _logger.info("Denied login request %s for chat %s", req.id, req.chat_id.chat_id)
