"""Business policy for explicit remove-before-reinstall workflows.

The policy deliberately keeps replacement date separate from damage: a battery may be
removed for replacement and remain reusable unless its removal reason explicitly
reports damage.
"""


def require_explicit_removal(movement_type: str, reason: str | None, *, resource_label: str):
    if movement_type == "remove" and not (reason or "").strip():
        raise ValueError(f"سبب فك {resource_label} إلزامي")
    if movement_type == "move":
        raise ValueError(
            f"نقل {resource_label} المباشر غير مسموح. يجب تسجيل الفك أولًا بسبب واضح، ثم تسجيل التركيب في الموقع الجديد."
        )


def require_free_before_install(*, movement_type: str, currently_installed: bool, resource_label: str):
    if movement_type == "install" and currently_installed:
        raise ValueError(
            f"لا يمكن تركيب {resource_label} جديد قبل تسجيل فك {resource_label} المركب حاليًا."
        )
