"""
QoI Protocol Messages.

Mirrors PBFT message types adapted for DNN inference:
  PRE_PREPARE  — primary broadcasts its argmax + probs to all replicas
  PREPARE      — each replica broadcasts its own argmax + probs
  COMMIT       — each replica confirms it has seen 2f+1 matching PREPAREs
  VIEW_CHANGE  — replica suspects primary is faulty, requests new view
  NEW_VIEW     — new primary announces it has taken over

All messages are signed by the sender (signature field).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.blockchain.utils import sha256_json, now


class MsgType(str, Enum):
    PRE_PREPARE  = "pre_prepare"
    PREPARE      = "prepare"
    COMMIT       = "commit"
    VIEW_CHANGE  = "view_change"
    NEW_VIEW     = "new_view"


# ── Base ──────────────────────────────────────────────────────────────────────

@dataclass
class BaseMessage:
    msg_type:   MsgType
    view:       int
    seq:        int          # sequence number — monotonic per view
    sender_id:  str          # node address (40-char hex)
    timestamp:  float        = field(default_factory=now)
    signature:  Optional[str] = None

    @property
    def msg_id(self) -> str:
        return sha256_json({
            "msg_type":  self.msg_type.value,
            "view":      self.view,
            "seq":       self.seq,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
        })

    def to_dict(self) -> dict:
        return {
            "msg_type":  self.msg_type.value,
            "view":      self.view,
            "seq":       self.seq,
            "sender_id": self.sender_id,
            "timestamp": self.timestamp,
            "signature": self.signature,
        }


# ── PRE_PREPARE ───────────────────────────────────────────────────────────────

@dataclass
class PrePrepareMsg(BaseMessage):
    """
    Sent by the primary node to kick off a consensus round.
    Carries the primary's own CNN inference result.
    """
    request_id:      str         = ""
    image_hash:      str         = ""
    probabilities:   list[float] = field(default_factory=list)
    predicted_class: int         = -1

    def __post_init__(self):
        self.msg_type = MsgType.PRE_PREPARE

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "request_id":      self.request_id,
            "image_hash":      self.image_hash,
            "probabilities":   self.probabilities,
            "predicted_class": self.predicted_class,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PrePrepareMsg:
        return cls(
            msg_type        = MsgType.PRE_PREPARE,
            view            = d["view"],
            seq             = d["seq"],
            sender_id       = d["sender_id"],
            timestamp       = d["timestamp"],
            signature       = d.get("signature"),
            request_id      = d["request_id"],
            image_hash      = d["image_hash"],
            probabilities   = d["probabilities"],
            predicted_class = d["predicted_class"],
        )


# ── PREPARE ───────────────────────────────────────────────────────────────────

@dataclass
class PrepareMsg(BaseMessage):
    """
    Sent by each replica after receiving PRE_PREPARE.
    Carries the replica's own CNN inference result.
    """
    request_id:      str         = ""
    probabilities:   list[float] = field(default_factory=list)
    predicted_class: int         = -1

    def __post_init__(self):
        self.msg_type = MsgType.PREPARE

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "request_id":      self.request_id,
            "probabilities":   self.probabilities,
            "predicted_class": self.predicted_class,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> PrepareMsg:
        return cls(
            msg_type        = MsgType.PREPARE,
            view            = d["view"],
            seq             = d["seq"],
            sender_id       = d["sender_id"],
            timestamp       = d["timestamp"],
            signature       = d.get("signature"),
            request_id      = d["request_id"],
            probabilities   = d["probabilities"],
            predicted_class = d["predicted_class"],
        )


# ── COMMIT ────────────────────────────────────────────────────────────────────

@dataclass
class CommitMsg(BaseMessage):
    """
    Sent by each replica after collecting 2f+1 matching PREPAREs.
    Confirms readiness to commit the consensus class.
    """
    request_id:       str = ""
    consensus_class:  int = -1   # the agreed argmax

    def __post_init__(self):
        self.msg_type = MsgType.COMMIT

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "request_id":      self.request_id,
            "consensus_class": self.consensus_class,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> CommitMsg:
        return cls(
            msg_type        = MsgType.COMMIT,
            view            = d["view"],
            seq             = d["seq"],
            sender_id       = d["sender_id"],
            timestamp       = d["timestamp"],
            signature       = d.get("signature"),
            request_id      = d["request_id"],
            consensus_class = d["consensus_class"],
        )


# ── VIEW_CHANGE ───────────────────────────────────────────────────────────────

@dataclass
class ViewChangeMsg(BaseMessage):
    """
    Sent by a replica that suspects the primary is faulty.
    Triggers election of a new primary for new_view.
    """
    new_view:   int = -1
    last_seq:   int = -1    # last sequence number the sender committed

    def __post_init__(self):
        self.msg_type = MsgType.VIEW_CHANGE

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "new_view": self.new_view,
            "last_seq": self.last_seq,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ViewChangeMsg:
        return cls(
            msg_type  = MsgType.VIEW_CHANGE,
            view      = d["view"],
            seq       = d["seq"],
            sender_id = d["sender_id"],
            timestamp = d["timestamp"],
            signature = d.get("signature"),
            new_view  = d["new_view"],
            last_seq  = d["last_seq"],
        )


# ── NEW_VIEW ──────────────────────────────────────────────────────────────────

@dataclass
class NewViewMsg(BaseMessage):
    """
    Sent by the new primary after collecting 2f+1 VIEW_CHANGE messages.
    Announces the new view and resumes protocol.
    """
    new_view:         int        = -1
    view_change_msgs: list[dict] = field(default_factory=list)  # serialised ViewChangeMsgs

    def __post_init__(self):
        self.msg_type = MsgType.NEW_VIEW

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({
            "new_view":         self.new_view,
            "view_change_msgs": self.view_change_msgs,
        })
        return d

    @classmethod
    def from_dict(cls, d: dict) -> NewViewMsg:
        return cls(
            msg_type          = MsgType.NEW_VIEW,
            view              = d["view"],
            seq               = d["seq"],
            sender_id         = d["sender_id"],
            timestamp         = d["timestamp"],
            signature         = d.get("signature"),
            new_view          = d["new_view"],
            view_change_msgs  = d["view_change_msgs"],
        )


# ── Factory ───────────────────────────────────────────────────────────────────

def message_from_dict(d: dict) -> BaseMessage:
    match MsgType(d["msg_type"]):
        case MsgType.PRE_PREPARE:  return PrePrepareMsg.from_dict(d)
        case MsgType.PREPARE:      return PrepareMsg.from_dict(d)
        case MsgType.COMMIT:       return CommitMsg.from_dict(d)
        case MsgType.VIEW_CHANGE:  return ViewChangeMsg.from_dict(d)
        case MsgType.NEW_VIEW:     return NewViewMsg.from_dict(d)
        case _: raise ValueError(f"Unknown message type: {d['msg_type']}")
