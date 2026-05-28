from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.channels.telegram import TelegramChannel
from app.models.agent import Agent
from app.models.channel_link import CHANNEL_TYPE_TELEGRAM, ChannelLink
from app.repositories.agent_repository import AgentRepository
from app.repositories.channel_repository import ChannelRepository
from app.repositories.run_repository import RunRepository
from app.repositories.workflow_repository import WorkflowRepository
from app.services.agent_chat_service import AgentChatService
from app.services.run_service import RunExecutionError, RunService
from app.services.workflow_service import WorkflowService

logger = logging.getLogger(__name__)

TELEGRAM_LAUNCH_COMMANDS = frozenset({"/launch", "/pipeline", "/product-launch"})
TELEGRAM_BUILD_COMMANDS = frozenset({"/build", "/devsite", "/dev"})
TELEGRAM_HELP_TEXT = (
    "Orqestra Telegram commands:\n"
    "/launch — run the 5-agent Product Launch pipeline (default brief)\n"
    "/launch <text> — same pipeline with your custom brief\n"
    "/build — build & deploy a website (6-agent dev pipeline, default brief)\n"
    "/build <description> — same pipeline for any business (restaurant, salon, etc.)\n"
    "/chat <message> — talk to the linked agent (1:1)\n"
    "/reset — clear chat history\n"
    "/help — show this message"
)


class ChannelNotFound(Exception):
    pass


class ChannelValidationError(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__(str(errors))


class ChannelService:
    def __init__(
        self,
        channel_repo: ChannelRepository,
        agent_repo: AgentRepository,
        run_repo: RunRepository,
        workflow_repo: WorkflowRepository,
    ) -> None:
        self.channel_repo = channel_repo
        self.agent_repo = agent_repo
        self.run_repo = run_repo
        self.workflow_repo = workflow_repo
        self._telegram = TelegramChannel()
        self._chat = AgentChatService(run_repo)

    def link_detail(self, link: ChannelLink) -> dict[str, Any]:
        return self._to_detail(link)

    def list_links(self) -> list[dict[str, Any]]:
        rows = []
        for link in self.channel_repo.list_all():
            rows.append(self.link_detail(link))
        return rows

    def get_link(self, link_id: int) -> dict[str, Any]:
        link = self.channel_repo.get_by_id(link_id)
        if not link:
            raise ChannelNotFound(f"Channel link {link_id} not found")
        return self._to_detail(link)

    def link_agent(
        self,
        *,
        agent_id: int,
        channel_type: str,
        chat_id: str,
        is_active: bool = True,
    ) -> ChannelLink:
        errors: dict[str, str] = {}
        chat_id = str(chat_id).strip()
        if not chat_id:
            errors["chat_id"] = "Telegram chat ID is required."
        agent = self.agent_repo.get_by_id(agent_id)
        if not agent:
            errors["agent_id"] = "Agent not found."
        if channel_type != CHANNEL_TYPE_TELEGRAM:
            errors["channel_type"] = "Only telegram is supported in this release."
        if errors:
            raise ChannelValidationError(errors)

        existing = self.channel_repo.get_telegram_by_chat_id(chat_id)
        if existing and existing.agent_id != agent_id:
            errors["chat_id"] = "This chat is already linked to another agent."
            raise ChannelValidationError(errors)

        prior = self.channel_repo.get_active_telegram_for_agent(agent_id)
        if prior:
            config = dict(prior.config or {})
            config["chat_id"] = chat_id
            return self.channel_repo.update(prior, config=config, is_active=is_active)

        return self.channel_repo.create(
            agent_id=agent_id,
            channel_type=channel_type,
            config={"chat_id": chat_id},
            is_active=is_active,
        )

    def delete_link(self, link_id: int) -> None:
        link = self.channel_repo.get_by_id(link_id)
        if not link:
            raise ChannelNotFound(f"Channel link {link_id} not found")
        self.channel_repo.delete(link)

    def handle_telegram_update(self, payload: dict) -> dict[str, Any]:
        inbound = self._telegram.parse_inbound(payload)
        if inbound is None:
            return {"ok": True, "skipped": "no_text_message"}

        link = self.channel_repo.get_telegram_by_chat_id(inbound.chat_id)
        if not link or not link.is_active:
            logger.info("Telegram message from unlinked chat_id=%s", inbound.chat_id)
            return {"ok": True, "skipped": "unlinked_chat"}

        agent = link.agent or self.agent_repo.get_by_id(link.agent_id)
        if not agent or not agent.is_active:
            return {"ok": True, "skipped": "inactive_agent"}

        text = inbound.text.strip()
        lower = text.lower()

        if lower in ("/help", "/start"):
            self.send_telegram_message(inbound.chat_id, TELEGRAM_HELP_TEXT)
            return {"ok": True, "help": True}

        if lower == "/reset":
            return self._reset_conversation(link)

        if self._is_launch_command(text):
            return self._trigger_launch_pipeline(link, inbound.chat_id, text)

        if self._is_build_command(text):
            return self._trigger_build_pipeline(link, inbound.chat_id, text)

        if lower.startswith("/chat"):
            user_message = text[5:].strip() or "Hello"
        else:
            user_message = text

        run_id = self._ensure_conversation_run(link)
        reply = self._chat.generate_reply(
            agent=agent,
            user_message=user_message,
            run_id=run_id,
        )
        send_result = self.send_telegram_message(inbound.chat_id, reply)
        return {
            "ok": True,
            "run_id": run_id,
            "agent_id": agent.id,
            "telegram": send_result,
        }

    def send_telegram_message(self, chat_id: str, text: str) -> dict:
        if not self._telegram.is_configured():
            logger.info("Telegram send skipped (no token): %s", text[:80])
            return {"ok": False, "skipped": True, "reason": "not_configured"}
        try:
            return self._telegram.send_message(chat_id, text)
        except Exception as exc:
            logger.exception("Telegram send failed")
            return {"ok": False, "error": str(exc)}

    def deliver_workflow_notification(
        self,
        *,
        run_id: int,
        agent_id: int | None,
        channel: str,
        text: str,
    ) -> dict:
        if channel != CHANNEL_TYPE_TELEGRAM:
            return {"ok": True, "skipped": True, "channel": channel}

        chat_id = self._telegram_chat_id_for_run(run_id)
        link = None
        if not chat_id and agent_id is not None:
            link = self.channel_repo.get_active_telegram_for_agent(agent_id)
        if not chat_id and not link:
            for candidate in self.channel_repo.list_all():
                if (
                    candidate.channel_type == CHANNEL_TYPE_TELEGRAM
                    and candidate.is_active
                ):
                    link = candidate
                    break

        if not chat_id and link:
            chat_id = str((link.config or {}).get("chat_id", ""))

        if not chat_id:
            self.run_repo.add_log(
                run_id=run_id,
                level="warning",
                message="Telegram notify skipped: no channel link configured",
            )
            return {"ok": False, "skipped": True, "reason": "no_link"}

        run = self.run_repo.get_run(run_id)
        body = text
        if run and run.triggered_by == "telegram":
            body = f"{text}\n\n— Run #{run_id} · view logs in Orqestra"

        result = self.send_telegram_message(chat_id, body)
        self.run_repo.add_log(
            run_id=run_id,
            level="info",
            message="Workflow notification sent via Telegram",
            metadata={"chat_id": chat_id, "agent_id": agent_id, "result": result},
        )
        return result

    def notify_telegram_run_failed(self, run_id: int, *, error: str) -> dict:
        chat_id = self._telegram_chat_id_for_run(run_id)
        if not chat_id:
            return {"ok": False, "skipped": True, "reason": "no_chat_id"}
        message = f"Pipeline run #{run_id} failed.\n\n{error[:1500]}"
        return self.send_telegram_message(chat_id, message)

    @staticmethod
    def _is_launch_command(text: str) -> bool:
        stripped = text.strip()
        lower = stripped.lower()
        if lower in TELEGRAM_LAUNCH_COMMANDS:
            return True
        return lower.startswith(("/launch ", "/pipeline ", "launch:", "pipeline:"))

    @staticmethod
    def _parse_launch_task_input(text: str) -> str:
        stripped = text.strip()
        lower = stripped.lower()
        prefixes = (
            "/product-launch",
            "/pipeline",
            "/launch",
            "pipeline:",
            "launch:",
        )
        for prefix in prefixes:
            if lower.startswith(prefix):
                rest = stripped[len(prefix) :].strip()
                return rest or WorkflowService.E2E_DEFAULT_TASK_INPUT
        if lower in TELEGRAM_LAUNCH_COMMANDS:
            return WorkflowService.E2E_DEFAULT_TASK_INPUT
        return stripped

    def _resolve_e2e_workflow(self):
        workflow = self.workflow_repo.get_by_name(
            WorkflowService.E2E_RUN_WORKFLOW_NAME,
            is_template=False,
        )
        if workflow:
            return workflow
        return self.workflow_repo.get_by_name(
            WorkflowService.E2E_TEMPLATE_NAME,
            is_template=True,
        )

    def _trigger_launch_pipeline(
        self,
        link: ChannelLink,
        chat_id: str,
        text: str,
    ) -> dict[str, Any]:
        workflow = self._resolve_e2e_workflow()
        if not workflow:
            self.send_telegram_message(
                chat_id,
                "Product Launch pipeline is not seeded yet. "
                "Run: bash scripts/seed_e2e_demo.sh",
            )
            return {"ok": False, "error": "workflow_not_found"}

        task_input = self._parse_launch_task_input(text)
        run_service = RunService(
            self.run_repo,
            self.workflow_repo,
            self.agent_repo,
        )
        run = run_service.enqueue_run(
            workflow.id,
            task_input=task_input,
            triggered_by="telegram",
            telegram_chat_id=chat_id,
        )
        ack = (
            f"Product launch pipeline started (Run #{run.id}).\n"
            "Five agents are working: intake → research → strategy → copy → review.\n"
            "You will receive the final announcement here when complete "
            "(usually 1–3 minutes)."
        )
        send_result = self.send_telegram_message(chat_id, ack)
        return {
            "ok": True,
            "mode": "workflow_launch",
            "run_id": run.id,
            "workflow_id": workflow.id,
            "telegram": send_result,
        }

    @staticmethod
    def _is_build_command(text: str) -> bool:
        stripped = text.strip()
        lower = stripped.lower()
        if lower in TELEGRAM_BUILD_COMMANDS:
            return True
        return any(lower.startswith(cmd + " ") for cmd in TELEGRAM_BUILD_COMMANDS)

    @staticmethod
    def _parse_build_task_input(text: str) -> str:
        stripped = text.strip()
        lower = stripped.lower()
        for cmd in sorted(TELEGRAM_BUILD_COMMANDS, key=len, reverse=True):
            if lower.startswith(cmd + " "):
                rest = stripped[len(cmd):].strip()
                if rest:
                    return rest
            elif lower == cmd:
                return WorkflowService.DEV_DEFAULT_TASK_INPUT
        return stripped or WorkflowService.DEV_DEFAULT_TASK_INPUT

    def _resolve_dev_workflow(self):
        for name in (
            WorkflowService.DEV_RUN_WORKFLOW_NAME,
            WorkflowService.DEV_RUN_WORKFLOW_LEGACY_NAME,
        ):
            workflow = self.workflow_repo.get_by_name(name, is_template=False)
            if workflow:
                return workflow
        return self.workflow_repo.get_by_name(
            WorkflowService.DEV_TEMPLATE_NAME,
            is_template=True,
        )

    def _trigger_build_pipeline(
        self,
        link: ChannelLink,
        chat_id: str,
        text: str,
    ) -> dict[str, Any]:
        workflow = self._resolve_dev_workflow()
        if not workflow:
            self.send_telegram_message(
                chat_id,
                "Dev pipeline is not seeded yet. Restart the platform or run the seed script.",
            )
            return {"ok": False, "error": "workflow_not_found"}

        task_input = self._parse_build_task_input(text)
        run_service = RunService(
            self.run_repo,
            self.workflow_repo,
            self.agent_repo,
        )
        run = run_service.enqueue_run(
            workflow.id,
            task_input=task_input,
            triggered_by="telegram",
            telegram_chat_id=chat_id,
        )
        ack = (
            f"Dev pipeline started (Run #{run.id}).\n"
            "Six agents are working: Planner → Backend → Frontend → Reviewer → Tester → DevOps.\n"
            "I will send the live URL here when the site is deployed (usually 8–12 minutes)."
        )
        send_result = self.send_telegram_message(chat_id, ack)
        return {
            "ok": True,
            "mode": "build_pipeline",
            "run_id": run.id,
            "workflow_id": workflow.id,
            "telegram": send_result,
        }

    def _telegram_chat_id_for_run(self, run_id: int) -> str:
        for log in self.run_repo.list_logs(run_id):
            metadata = log.log_metadata or {}
            chat_id = metadata.get("telegram_chat_id")
            if chat_id:
                return str(chat_id).strip()
        return ""

    def _reset_conversation(self, link: ChannelLink) -> dict[str, Any]:
        config = dict(link.config or {})
        config.pop("conversation_run_id", None)
        self.channel_repo.update_config(link, config)
        chat_id = str(config.get("chat_id", ""))
        if chat_id:
            self.send_telegram_message(
                chat_id,
                "Conversation reset. Send a new message to start fresh.",
            )
        return {"ok": True, "reset": True}

    def _ensure_conversation_run(self, link: ChannelLink) -> int:
        config = dict(link.config or {})
        run_id = config.get("conversation_run_id")
        if run_id:
            existing = self.run_repo.get_run(int(run_id))
            if existing:
                return int(run_id)

        workflow = self.workflow_repo.get_by_name(
            WorkflowService.DEMO_WORKFLOW_NAME,
            is_template=False,
        )
        if not workflow:
            workflows = self.workflow_repo.list_all(templates_only=False)
            workflow = workflows[0] if workflows else None
        if not workflow:
            raise RunExecutionError(
                "No workflow available for Telegram conversation logging"
            )

        run = self.run_repo.create_run(
            workflow_id=workflow.id,
            triggered_by="telegram",
        )
        self.run_repo.add_log(
            run_id=run.id,
            level="info",
            message="Telegram conversation run started",
            metadata={
                "agent_id": link.agent_id,
                "chat_id": config.get("chat_id"),
            },
        )
        config["conversation_run_id"] = run.id
        self.channel_repo.update_config(link, config)
        return run.id

    @staticmethod
    def _to_detail(link: ChannelLink) -> dict[str, Any]:
        config = link.config or {}
        agent_name = link.agent.name if link.agent else None
        return {
            "id": link.id,
            "agent_id": link.agent_id,
            "agent_name": agent_name,
            "channel_type": link.channel_type,
            "config": config,
            "chat_id": str(config.get("chat_id", "")),
            "conversation_run_id": config.get("conversation_run_id"),
            "is_active": link.is_active,
            "created_at": link.created_at,
            "updated_at": link.updated_at,
        }


def build_channel_service(db: Session) -> ChannelService:
    return ChannelService(
        ChannelRepository(db),
        AgentRepository(db),
        RunRepository(db),
        WorkflowRepository(db),
    )
