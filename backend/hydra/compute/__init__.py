"""Phase-3 gated compute subsystem (branch 03-03).

Additive, sandboxed execution built on top of the Phase-1/2 infrastructure. It
never touches or widens the Phase-1/2 safe command console; every run here is
resource-bounded, network-restricted, approval-gated, checkpointed and audited.
"""
