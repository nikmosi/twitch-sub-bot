from __future__ import annotations

import asyncio
from collections.abc import Sequence

import httpx
from loguru import logger

from twitch_subs.application.error import WatcherRunError
from twitch_subs.application.logins import LoginsProvider
from twitch_subs.domain.events import (
    LoopChecked,
    LoopCheckFailed,
    OnceChecked,
    UserBecameSubscribable,
)
from twitch_subs.domain.models import BroadcasterType, SubState, UserRecord

from .ports import (
    EventBus,
    NotifierProtocol,
    SubscriptionStateRepo,
    TwitchClientProtocol,
)


class Watcher:
    """Monitor Twitch logins and notify when subscription becomes available."""

    def __init__(
        self,
        twitch: TwitchClientProtocol,
        notifier: NotifierProtocol,
        state_repo: SubscriptionStateRepo,
        event_bus: EventBus,
    ) -> None:
        self.twitch = twitch
        self.notifier = notifier
        self.state_repo = state_repo
        self.event_bus = event_bus

    async def check_logins(self, logins: str | Sequence[str]) -> Sequence[UserRecord]:
        if isinstance(logins, str):
            logins = [logins]
        users = await self.twitch.get_users_by_login(logins)

        if not users:
            logger.warning("[Watcher] No users found for requested logins: {}", logins)
            return []

        return users

    def _get_sub_state_or_default(self, user: UserRecord) -> SubState:
        previous_state = self.state_repo.get_sub_state(user.login)
        if not previous_state:
            previous_state = SubState(
                login=user.login, broadcaster_type=BroadcasterType.NONE
            )
        return previous_state

    def _became_subscribable(self, user: UserRecord) -> bool:
        current_state = user.broadcaster_type
        previous_state = self._get_sub_state_or_default(user)

        was_subscribable = previous_state.is_subscribed
        is_subscribable = current_state.is_subscribable()

        return is_subscribable and was_subscribable != is_subscribable

    def _to_sub_state(self, user: UserRecord) -> SubState:
        current_state = user.broadcaster_type
        previous_state = self._get_sub_state_or_default(user)

        return SubState(
            login=user.login,
            broadcaster_type=current_state,
            since=previous_state.since,
        )

    async def _build_current_states(
        self, users: Sequence[UserRecord]
    ) -> Sequence[SubState]:
        current_states: list[SubState] = []

        for user in users:
            if self._became_subscribable(user):
                await self.event_bus.publish(
                    UserBecameSubscribable(
                        login=user.login, current_state=user.broadcaster_type
                    )
                )

            await self.event_bus.publish(
                OnceChecked(login=user.login, current_state=user.broadcaster_type)
            )

            current_states.append(self._to_sub_state(user))
        return current_states

    async def run_once(self, logins: Sequence[str]) -> None:
        try:
            users = await self.check_logins(logins)
        except httpx.TimeoutException as e:
            await self.event_bus.publish(LoopCheckFailed(logins=logins, error=str(e)))
            return

        found_logins = tuple(user.login for user in users)
        found_set = set(found_logins)
        missing_logins = tuple(login for login in logins if login not in found_set)
        states = await self._build_current_states(users)
        self.state_repo.set_many(list(states))

        await self.event_bus.publish(
            LoopChecked(
                found_logins=found_logins,
                missing_logins=missing_logins,
            )
        )

    async def watch(
        self,
        logins_provider: LoginsProvider,
        interval: int,
        stop_event: asyncio.Event,
    ) -> None:
        """Run the watcher until *stop_event* is set."""

        await self.notifier.notify_about_start()
        try:
            while not stop_event.is_set():
                all_logins = logins_provider.get()
                try:
                    await self.run_once(all_logins)
                except Exception as e:
                    logger.opt(exception=e).exception(
                        "[Watcher] run_once failed for logins={}: {}", all_logins, e
                    )
                    await self.event_bus.publish(
                        LoopCheckFailed(logins=tuple(all_logins), error=str(e))
                    )
                    raise WatcherRunError(logins=tuple(all_logins), error=e)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval)
                except TimeoutError:
                    pass
        finally:
            logger.info("[Watcher] Notifying about watcher stop event to notifier.")
            await asyncio.shield(self.notifier.notify_about_stop())
