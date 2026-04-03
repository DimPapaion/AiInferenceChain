"""
Message Handler for QoI Consensus.

Wraps QoIStateMachine to provide event-driven message handling.
Automates:
  - Message signing
  - Broadcasting responses
  - Emitting consensus events
  - Timeout scheduling

Usage:
    handler = QoIMessageHandler(
        node_id="abc...",
        primary_id="def...",
        node=node,  # for callbacks
    )
    
    # Messages come in from network/other nodes
    handler.on_message_received(pre_prepare_msg)
    
    # Handler automatically:
    # - validates message
    # - updates internal state
    # - emits QOI_PREPARE event
    # - calls node.sign(prepare_msg)
    # - publishes PREPARE to event bus
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Any, Callable

from core.qoi.state_machine import QoIStateMachine, QoIPhase, ConsensusOutcome
from core.qoi.timeout_manager import TimeoutManager
from core.qoi.messages import (
    BaseMessage, MsgType,
    PrePrepareMsg, PrepareMsg, CommitMsg, ViewChangeMsg, NewViewMsg,
)
from core.events import EventBus, EventType, ConsensusEvent, get_global_bus
from core.utils.logger import get_logger


@dataclass
class QoIMessageHandlerConfig:
    """Configuration for message handler."""
    node_id: str
    primary_id: str
    f: int = 1
    timeout_seconds: float = 10.0


class QoIMessageHandler:
    """
    Event-driven wrapper around QoIStateMachine.
    
    Responsibilities:
    - Own the state machine lifecycle
    - Handle incoming messages
    - Emit consensus events
    - Manage timeouts (scheduled, not polled)
    - Call node for model inference + signing
    """
    
    def __init__(
        self,
        config: QoIMessageHandlerConfig,
        node: Any = None,  # Inference node; used for callbacks
        event_bus: Optional[EventBus] = None,
    ):
        self.config = config
        self.node = node
        self.event_bus = event_bus or get_global_bus()
        self.logger = get_logger(f"qoi_handler_{config.node_id[:8]}")
        
        # State machine
        self.state_machine = QoIStateMachine(
            node_id=config.node_id,
            primary_id=config.primary_id,
            f=config.f,
        )
        
        # Round tracking
        self._current_trace_id: Optional[str] = None
        self._round_start_time: float = 0.0
        self._last_model_probs: list[float] = []

        # Deduplication: set of (view, seq, sender_id, msg_type) already processed
        self._seen_messages: set[tuple] = set()

        # Timeout manager — fires _on_timeout when a round stalls
        self._timeout_manager = TimeoutManager(
            timeout_secs=config.timeout_seconds,
            on_timeout=self._on_timeout_by_round,
        )

        # Subscribe to timeout events
        self.event_bus.subscribe(
            EventType.QOI_TIMEOUT,
            self._on_timeout,
            filter_fn=lambda e: e.data.get("node_id") == config.node_id,
        )
    
    def start_round(
        self,
        request_id: str,
        image_hash: str,
        seq: int,
        own_probs: list[float],
        trace_id: Optional[str] = None,
    ) -> Optional[PrePrepareMsg]:
        """
        Start a new QoI consensus round.
        
        If this node is primary, returns the PRE_PREPARE message to broadcast.
        Otherwise, returns None (waits for PRE_PREPARE from primary).
        """
        self._current_trace_id = trace_id or f"req-{request_id[:8]}"
        self._round_start_time = time.time()
        self._last_model_probs = own_probs
        self._seen_messages.clear()
        
        self.logger.info(
            "Starting QoI round",
            trace_id=self._current_trace_id,
            context={"seq": seq, "is_primary": self.state_machine.is_primary()},
        )
        
        # Start the state machine
        msg = self.state_machine.start_round(request_id, image_hash, seq, own_probs)
        
        if msg is not None:
            # This node is the primary
            self.logger.info(
                "Primary broadcasting PRE_PREPARE",
                trace_id=self._current_trace_id,
                context={"predicted_class": msg.predicted_class},
            )
            
            # Sign the message
            if self.node and hasattr(self.node, "identity"):
                msg.signature = self.node.identity.sign(msg.to_dict())
            
            # Emit event
            self.event_bus.publish(
                EventType.QOI_PRE_PREPARE,
                trace_id=self._current_trace_id,
                data={"message": msg.to_dict()},
            )
            
            # Schedule timeout for this round
            self._schedule_timeout(request_id)
        else:
            # This node is a replica; wait for PRE_PREPARE from primary
            self.logger.info(
                "Replica waiting for PRE_PREPARE",
                trace_id=self._current_trace_id,
            )

            # Schedule timeout
            self._schedule_timeout(request_id)
        
        return msg
    
    def on_message_received(self, msg: BaseMessage) -> None:
        """
        Handle an incoming consensus message.

        Called when a message arrives (from network, other nodes, etc).
        Automatically:
        - Validates the message (including dedup)
        - Updates state machine
        - Generates response if needed
        - Broadcasts response via event bus
        - Emits consensus events
        """
        # Deduplicate — same (view, seq, sender, type) is only processed once
        dedup_key = (
            getattr(msg, "view", None),
            getattr(msg, "seq", None),
            getattr(msg, "sender_id", None),
            msg.msg_type,
        )
        if dedup_key in self._seen_messages:
            return
        self._seen_messages.add(dedup_key)

        if msg.msg_type == MsgType.PRE_PREPARE:
            self._handle_pre_prepare(msg)
        elif msg.msg_type == MsgType.PREPARE:
            self._handle_prepare(msg)
        elif msg.msg_type == MsgType.COMMIT:
            self._handle_commit(msg)
        elif msg.msg_type == MsgType.VIEW_CHANGE:
            self._handle_view_change(msg)
        elif msg.msg_type == MsgType.NEW_VIEW:
            self._handle_new_view(msg)
    
    def _handle_pre_prepare(self, msg: PrePrepareMsg) -> None:
        """Handle incoming PRE_PREPARE message."""
        self.logger.info(
            "Received PRE_PREPARE",
            trace_id=msg.msg_id[:8],
            context={
                "sender": msg.sender_id[:8],
                "phase": self.state_machine.phase.name,
            },
        )
        
        # Feed to state machine
        response = self.state_machine.handle_message(msg)
        
        if response is not None:
            # State machine generated a PREPARE response
            self.logger.info(
                "Replica responding with PREPARE",
                trace_id=msg.msg_id[:8],
                context={"predicted_class": response.predicted_class},
            )
            
            # Sign it
            if self.node and hasattr(self.node, "identity"):
                response.signature = self.node.identity.sign(response.to_dict())
            
            # Emit and broadcast
            self.event_bus.publish(
                EventType.QOI_PREPARE,
                trace_id=msg.msg_id[:8],
                data={"message": response.to_dict()},
            )
    
    def _handle_prepare(self, msg: PrepareMsg) -> None:
        """Handle incoming PREPARE message."""
        self.logger.info(
            "Received PREPARE",
            trace_id=msg.msg_id[:8],
            context={"sender": msg.sender_id[:8]},
        )
        
        response = self.state_machine.handle_message(msg)
        
        if response is not None:
            # We've collected 2f+1 PREPAREs; emit COMMIT
            self.logger.info(
                "Quorum of PREPAREs reached; broadcasting COMMIT",
                trace_id=msg.msg_id[:8],
            )
            
            if self.node and hasattr(self.node, "identity"):
                response.signature = self.node.identity.sign(response.to_dict())
            
            self.event_bus.publish(
                EventType.QOI_COMMIT,
                trace_id=msg.msg_id[:8],
                data={"message": response.to_dict()},
            )
    
    def _handle_commit(self, msg: CommitMsg) -> None:
        """Handle incoming COMMIT message."""
        self.logger.info(
            "Received COMMIT",
            trace_id=msg.msg_id[:8],
            context={"sender": msg.sender_id[:8]},
        )
        
        old_phase = self.state_machine.phase
        response = self.state_machine.handle_message(msg)
        new_phase = self.state_machine.phase
        
        if new_phase == QoIPhase.COMMITTED and old_phase != QoIPhase.COMMITTED:
            # Consensus reached!
            self.logger.info(
                "Consensus committed! Emitting outcome",
                trace_id=msg.msg_id[:8],
            )

            # Emit event with outcome
            outcome = self.state_machine.outcome
            if outcome:
                self._cancel_timeout(outcome.request_id)
                self.event_bus.publish(
                    EventType.QOI_COMMITTED,
                    trace_id=msg.msg_id[:8],
                    data={
                        "request_id": outcome.request_id,
                        "consensus_class": outcome.consensus_class,
                        "view": outcome.view,
                    },
                )
    
    def _handle_view_change(self, msg: ViewChangeMsg) -> None:
        """Handle incoming VIEW_CHANGE message."""
        self.logger.warn(
            "Received VIEW_CHANGE; view change detected",
            trace_id=msg.msg_id[:8],
            context={"new_view": msg.view},
        )
        
        response = self.state_machine.handle_message(msg)
        
        if response is not None and isinstance(response, NewViewMsg):
            # We collected 2f+1 VIEW_CHANGEs and are new primary
            self.logger.info(
                "New primary broadcasting NEW_VIEW",
                trace_id=msg.msg_id[:8],
            )
            
            if self.node and hasattr(self.node, "identity"):
                response.signature = self.node.identity.sign(response.to_dict())
            
            self.event_bus.publish(
                EventType.QOI_NEW_VIEW,
                trace_id=msg.msg_id[:8],
                data={"view": response.view},
            )
    
    def _handle_new_view(self, msg: NewViewMsg) -> None:
        """Handle incoming NEW_VIEW message."""
        self.logger.info(
            "Received NEW_VIEW; primary changed",
            trace_id=msg.msg_id[:8],
            context={"new_view": msg.view},
        )
        
        self.state_machine.handle_message(msg)
    
    def _schedule_timeout(self, request_id: str) -> None:
        """Register the current round with TimeoutManager so view changes fire automatically."""
        self._timeout_manager.start_round(
            round_id=request_id,
            view=self.state_machine.view,
        )
        self.logger.debug(
            "Timeout scheduled",
            trace_id=self._current_trace_id,
            context={"timeout_seconds": self.config.timeout_seconds},
        )

    def _cancel_timeout(self, request_id: str) -> None:
        """Stop tracking a round after it commits successfully."""
        self._timeout_manager.end_round(request_id)

    def _on_timeout_by_round(self, round_id: str, view: int) -> None:
        """Called by TimeoutManager when a round times out."""
        self.logger.warn(
            "Round timeout (TimeoutManager); triggering view change",
            trace_id=self._current_trace_id,
            context={"round_id": round_id, "view": view},
        )
        vc_msg = self.state_machine.check_timeout(self._last_model_probs)
        if vc_msg is not None:
            if self.node and hasattr(self.node, "identity"):
                vc_msg.signature = self.node.identity.sign(vc_msg.to_dict())
            self.event_bus.publish(
                EventType.QOI_VIEW_CHANGE,
                trace_id=self._current_trace_id or round_id,
                data={"message": vc_msg.to_dict()},
            )
    
    def _on_timeout(self, event: ConsensusEvent) -> None:
        """Handle a timeout event."""
        self.logger.warn(
            "Round timeout; triggering view change",
            trace_id=event.trace_id,
        )
        
        # Generate VIEW_CHANGE message
        vc_msg = self.state_machine.check_timeout(self._last_model_probs)
        
        if vc_msg is not None:
            self.logger.info(
                "Broadcasting VIEW_CHANGE",
                trace_id=event.trace_id,
                context={"new_view": vc_msg.view},
            )
            
            if self.node and hasattr(self.node, "identity"):
                vc_msg.signature = self.node.identity.sign(vc_msg.to_dict())
            
            self.event_bus.publish(
                EventType.QOI_VIEW_CHANGE,
                trace_id=event.trace_id,
                data={"message": vc_msg.to_dict()},
            )
    
    @property
    def phase(self) -> QoIPhase:
        """Current consensus phase."""
        return self.state_machine.phase
    
    @property
    def outcome(self) -> Optional[ConsensusOutcome]:
        """Consensus outcome (if round completed)."""
        return self.state_machine.outcome
    
    def __repr__(self) -> str:
        return (
            f"QoIMessageHandler(node={self.config.node_id[:8]}, "
            f"primary={self.config.primary_id[:8]}, "
            f"phase={self.state_machine.phase.name})"
        )
