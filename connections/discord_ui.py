"""Private, deterministic Discord controls. No authentication decision uses an LLM."""
from __future__ import annotations

import asyncio
import discord
from discord.ext import commands, tasks

from .security import ConnectionError
from .service import BOTS

MESSAGES = {
    "NOT_CONFIGURED": "Google Connect is not configured by the operator yet. No account was connected.",
    "NOT_CONNECTED": "Google isn't connected yet. Use Connect Google below.",
    "BOT_DISABLED": "This bot does not have permission to use your Google connection. Manage its grant below.",
    "REAUTH_REQUIRED": "Google needs to be reconnected.",
    "SCOPES_MISSING": "The requested Google permission was not granted. Reconnect to review Calendar and Tasks permissions.",
    "RATE_LIMITED": "Too many connection attempts. Please wait 15 minutes before trying again.",
    "INVALID_SESSION": "That confirmation expired or was already used. Run !google again.",
    "ACCOUNT_CHANGED": "Your Google connection changed. Run !google for a fresh account panel.",
}


class OwnerView(discord.ui.View):
    def __init__(self, controller, user_id):
        super().__init__(timeout=600)
        self.controller, self.user_id = controller, int(user_id)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This account panel belongs to someone else.", ephemeral=True)
            return False
        if await self.controller.deletion_pending(self.user_id):
            await interaction.response.send_message("Your privacy reset is still completing. Try again afterward.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction, error, item):
        # discord.py's default logs exception traces; never include provider/token details.
        message = MESSAGES.get(getattr(error, "code", ""), "The account operation could not be completed. Try !google again.")
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


class ConfirmLink(OwnerView):
    def __init__(self, controller, user_id, session_id):
        super().__init__(controller, user_id)
        self.session_id = session_id

    @discord.ui.button(label="Confirm account link", style=discord.ButtonStyle.success)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        await self.controller.service.confirm_link(self.user_id, self.controller.bot_name, self.session_id)
        await interaction.edit_original_response(content="Google connected. Only this bot is allowed initially. Use !google permissions to enable the other bot.", embed=None, view=None)
        self.stop()


class Disconnect(OwnerView):
    def __init__(self, controller, user_id, revision=None):
        super().__init__(controller, user_id)
        self.revision = revision

    @discord.ui.button(label="Confirm disconnect from both bots", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        result = await self.controller.service.disconnect(self.user_id, expected_revision=self.revision)
        await self.controller.runtime.forget(self.user_id)
        text = "Google disconnected locally from both bots. Stored credentials, grants, and pending links were removed."
        if result == "LOCAL_DELETED_REMOTE_UNVERIFIED":
            text += " Google revocation could not be verified; remove the app in your Google Account's third-party access settings too."
        await interaction.edit_original_response(content=text, embed=None, view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="Disconnect cancelled.", embed=None, view=None)
        self.stop()


class Manage(OwnerView):
    def __init__(self, controller, user_id, grants, revision):
        super().__init__(controller, user_id)
        for name in BOTS:
            enabled = bool(grants.get(name))
            button = discord.ui.Button(label=f"{'Disable' if enabled else 'Allow'} {name.title()}",
                                       style=discord.ButtonStyle.secondary)

            async def change(interaction, name=name, enabled=enabled):
                await interaction.response.defer(ephemeral=True)
                await controller.service.grant(self.user_id, name, not enabled, expected_revision=revision)
                await interaction.edit_original_response(content="Bot grant updated. Run !google permissions to see the current grants.", embed=None, view=None)
                self.stop()

            button.callback = change
            self.add_item(button)
        disconnect = discord.ui.Button(label="Disconnect", style=discord.ButtonStyle.danger)

        async def ask(interaction):
            await interaction.response.edit_message(content="Disconnect Google from BOTH bots? This also cancels pending connection links.", embed=None, view=Disconnect(controller, self.user_id, revision))

        disconnect.callback = ask
        self.add_item(disconnect)


class ConnectionsController(commands.Cog):
    def __init__(self, bot, service, runtime, bot_name, deletion_pending):
        self.bot, self.service, self.runtime = bot, service, runtime
        self.bot_name, self.deletion_pending = bot_name, deletion_pending

    async def panel(self, user, *, connect=False, disconnect=False):
        if await self.deletion_pending(user.id):
            raise ConnectionError("RESET_PENDING")
        status = await self.service.status(user.id)
        if disconnect:
            return "Disconnect Google from BOTH bots?", None, Disconnect(self, user.id, status.get("revision"))
        pending = await self.service.pending(user.id, self.bot_name)
        if pending:
            return ("A Google account approved this link: " + pending["masked_identity"] +
                    ". Confirm only if YOU just authorized it. Otherwise ignore this request and run !google disconnect.",
                    None, ConfirmLink(self, user.id, pending["id"]))
        embed = discord.Embed(title="Connected Accounts", color=0x5865F2)
        embed.add_field(name="Google", value=status["status"].replace("_", " ").title(), inline=False)
        if status.get("masked_identity"):
            embed.add_field(name="Account", value=discord.utils.escape_markdown(status["masked_identity"]), inline=False)
        embed.add_field(name="Current modules", value=", ".join(status["modules"]) or "None", inline=False)
        embed.add_field(name="Bot permissions", value="\n".join(
            f"{name.title()}: {'Allowed' if status['grants'].get(name) else 'Disabled'}" for name in BOTS), inline=False)
        embed.set_footer(text="Calendar/Tasks only. Writes still require a separate exact confirmation. Never send passwords here.")
        view = Manage(self, user.id, status["grants"], status["revision"]) if status["status"] == "CONNECTED" else OwnerView(self, user.id)
        content = None
        if connect or status["status"] != "CONNECTED":
            if self.service.configured:
                link = await self.service.create_session(user.id, self.bot_name)
                view.add_item(discord.ui.Button(label="Connect Google", style=discord.ButtonStyle.link, url=link))
            else:
                content = MESSAGES["NOT_CONFIGURED"]
        return content, embed, view

    async def send_panel(self, user, **kwargs):
        content, embed, view = await self.panel(user, **kwargs)
        await user.send(content=content, embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())

    async def command(self, ctx, action="status"):
        try:
            await self.send_panel(ctx.author, connect=action == "connect", disconnect=action == "disconnect")
            if ctx.guild:
                await ctx.reply("Account controls sent privately.", mention_author=False, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            await ctx.reply("I couldn't DM you. Open a DM with me, then run !connections there.", mention_author=False)
        except ConnectionError as exc:
            # No URL or account identity is ever sent publicly as a DM fallback.
            await ctx.reply(MESSAGES.get(exc.code, "Account controls are unavailable. Try again later."), mention_author=False)

    async def google_check(self, ctx):
        root = ctx.command.root_parent or ctx.command
        if root.name not in {"calendar", "tasks"}:
            return True
        try:
            if await self.deletion_pending(ctx.author.id):
                raise ConnectionError("RESET_PENDING")
            await self.service.authorize(ctx.author.id, self.bot_name, root.name)
            return True
        except ConnectionError:
            await self.command(ctx)
            return False

    @tasks.loop(seconds=15)
    async def notices(self):
        if not self.service.configured:
            return
        try:
            for row in await self.service.notification_candidates(self.bot_name):
                try:
                    user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(row["user_id"])
                    await self.send_panel(user)
                except (discord.HTTPException, ConnectionError):
                    pass  # !google restores the durable confirmation after a missed DM/restart.
        except Exception:
            pass  # Never log provider payloads; the panel remains the recovery path.

    async def ready(self):
        if self.bot.get_cog("ConnectionsController") is None:
            await self.bot.add_cog(self)
        if not self.notices.is_running():
            self.notices.start()

    async def cog_unload(self):
        worker = self.notices.get_task()
        self.notices.cancel()
        if worker:
            await asyncio.gather(worker, return_exceptions=True)

    def install(self):
        @self.bot.command(name="connections")
        async def connections_cmd(ctx):
            await self.command(ctx)

        @self.bot.group(name="google", invoke_without_command=True)
        async def google_cmd(ctx):
            await self.command(ctx)

        for action in ("connect", "status", "permissions", "disconnect"):
            # Hide the Python closure default from Discord's argument parser.
            def make_callback(action):
                async def callback(ctx):
                    await self.command(ctx, action)
                return callback
            google_cmd.add_command(commands.Command(make_callback(action), name=action))
        self.bot.add_check(self.google_check)
        self.bot.add_listener(self.ready, "on_ready")
        return self
