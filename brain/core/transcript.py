"""The shared transcript: the task plus every turn taken so far.

Pure data + rendering. It can produce the message list a given bot should see
next, mapping that bot's own turns to "assistant" and everyone else's to "user"
(from each bot's point of view, the other bot is the one it's talking to).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Turn:
    speaker: str  # a Bot.name
    text: str


@dataclass
class Transcript:
    task: str  # the assignment that seeds the conversation
    turns: list[Turn] = field(default_factory=list)
    converged: bool = False  # set True if a bot signalled early convergence

    def append(self, speaker: str, text: str) -> None:
        self.turns.append(Turn(speaker=speaker, text=text))

    def render_for(self, speaker: str) -> list[dict[str, str]]:
        """Messages to feed the model when `speaker` is about to talk.

        The task is presented as the opening user message. Then each past turn
        becomes "assistant" if it was this speaker's, else "user".
        """
        messages: list[dict[str, str]] = [{"role": "user", "content": self.task}]
        for turn in self.turns:
            role = "assistant" if turn.speaker == speaker else "user"
            messages.append({"role": role, "content": turn.text})
        return messages
