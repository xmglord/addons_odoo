import json
import logging

from odoo import http
from odoo.http import request
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)


class TelegramController(http.Controller):
    _command_handlers = {
        "/start": "_handle_start_command",
        "/help": "_handle_help_command",
        "/login": "_handle_login_command",
        "/whoami": "_handle_whoami_command",
        "/logout": "_handle_logout_command",
    }
    _public_commands = {"/start", "/help", "/login"}

    @http.route("/telegram/webhook/<string:token>", type="jsonrpc", auth="public", csrf=False, methods=["POST"])
    def webhook(self, token, **kwargs):
        bot = request.env["telegram.bot"].sudo().search([("token", "=", token)], limit=1)
        if not bot:
            return "OK"

        try:
            data = json.loads(request.httprequest.data)
            _logger.info("Received update for bot '%s': %s", bot.name, data)

            if "message" in data:
                message = data["message"]
                chat_id = message["chat"]["id"]
                chat = request.env["telegram.chat"].sudo()._find_or_create(chat_id, bot.id)

                if message.get("text", "").startswith("/"):
                    parts = message.get("text").split()
                    command = parts[0].split("@")[0]
                    args = parts[1:]
                    self._dispatch_command(bot, chat, command, args, message)
                else:
                    bot.send_message(chat_id, "I can only understand commands. Please type /help to see the list.")
            return "OK"
        except Exception as e:
            _logger.error("Error processing webhook for bot '%s': %s", bot.name, e)
            return "Error"

    def _dispatch_command(self, bot, chat, command, args, message):
        handler_name = self._command_handlers.get(command)
        if not handler_name:
            bot.send_message(chat.chat_id, f"Unknown command: `{command}`")
            return

        handler_method = getattr(self, handler_name)

        chat.invalidate_recordset(["user_id"])

        if command in self._public_commands:
            handler_method(bot, chat, args, message)
        elif chat.user_id:
            env_as_user = request.env(user=chat.user_id)
            bot_as_user = env_as_user["telegram.bot"].browse(bot.id)
            chat_as_user = env_as_user["telegram.chat"].browse(chat.id)
            handler_method(bot_as_user, chat_as_user, args, message)
        else:
            bot.send_message(
                chat.chat_id,
                f"You must be logged in to use `{command}`. " "Use `/login <your-odoo-email>` to request access.",
            )

    def _handle_start_command(self, bot, chat, args, message):
        welcome_message = f"Welcome to *{bot.name}*!\nType /help to see what I can do."
        bot.send_message(chat.chat_id, welcome_message)

    def _handle_help_command(self, bot, chat, args, message):
        """Handles the /help command based on the user's login status."""
        if chat.user_id:
            help_text = (
                "You are logged in. Here are the available commands:\n\n"
                "*/whoami* - Check your current logged-in status.\n"
                "*/logout* - Unlink your Telegram and Odoo accounts.\n"
                "*/help* - Display this help message."
            )
        else:
            help_text = (
                "You are not logged in. Here are the available commands:\n\n"
                "*/login* `<your-odoo-email>` - Request to link your Telegram account to your Odoo user.\n"
                "*/help* - Display this help message."
            )
        bot.send_message(chat.chat_id, help_text)

    def _handle_whoami_command(self, bot, chat, args, message):
        user_message = (
            f"You are logged in to Odoo as:\n" f"- *Name:* {chat.user_id.name}\n" f"- *Email:* {chat.user_id.login}"
        )
        bot.send_message(chat.chat_id, user_message)

    def _handle_logout_command(self, bot, chat, args, message):
        """Logs the user out by unlinking their chat from the Odoo user."""
        user_name = chat.user_id.name

        chat.sudo().write({"user_id": False})

        logout_message = "✅ You have been successfully logged out."
        bot.send_message(chat.chat_id, logout_message)

        _logger.info("User %s (from chat ID %s) has logged out.", user_name, chat.chat_id)

    def _handle_login_command(self, bot, chat, args, message):
        """Creates a login request for an administrator to approve."""
        if len(args) != 1:
            bot.send_message(chat.chat_id, "Invalid format. Please use:\n`/login <your-odoo-email>`")
            return

        telegram_user_info = message.get("from", {})
        telegram_username = telegram_user_info.get("username")
        first_name = telegram_user_info.get("first_name", "")
        last_name = telegram_user_info.get("last_name", "")
        telegram_full_name = f"{first_name} {last_name}".strip()
        if not telegram_username and not telegram_full_name:
            telegram_username = "Unknown Telegram User"

        odoo_login = args[0]
        user_sudo = request.env["res.users"].sudo().search([("login", "=", odoo_login)], limit=1)

        if not user_sudo:
            bot.send_message(chat.chat_id, f"❌ No Odoo user found with the email `{odoo_login}`.")
            return

        if request.env["telegram.chat"].sudo().search_count([("user_id", "=", user_sudo.id), ("bot_id", "=", bot.id)]):
            bot.send_message(chat.chat_id, "This Odoo user is already linked to this bot.")
            return

        if (
            request.env["telegram.login.request"]
            .sudo()
            .search_count([("chat_id", "=", chat.id), ("state", "=", "pending")])
        ):
            bot.send_message(
                chat.chat_id,
                "You already have a pending login request. Please wait for an administrator to approve it.",
            )
            return

        login_request = (
            request.env["telegram.login.request"]
            .sudo()
            .create(
                {
                    "chat_id": chat.id,
                    "telegram_username": telegram_username,
                    "telegram_user_full_name": telegram_full_name,
                    "requested_user_id": user_sudo.id,
                }
            )
        )

        bot.send_message(
            chat.chat_id, "✅ Your request to link accounts has been sent. An administrator will review it shortly."
        )

        self._notify_admins_of_request(bot, login_request)

    def _notify_admins_of_request(self, bot, login_request):
        """Constructs and sends a notification to the admin channel."""
        base_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")
        request_url = f"{base_url}/web#id={login_request.id}&" f"model=telegram.login.request&view_type=form"

        notification_html = (
            f"<p>🔔 <b>New Telegram Login Request</b></p>"
            f"<p>Telegram User: <b>@{html_escape(login_request.telegram_username)}</b></p>"
            f"<p>Wants to log in as Odoo User: <b>{html_escape(login_request.requested_user_id.name)}</b></p>"
            f"<p>Please <a href='{html_escape(request_url)}'>review the request</a> to approve or deny it.</p>"
        )

        bot.sudo()._post_notification(notification_html)
