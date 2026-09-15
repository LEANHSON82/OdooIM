"""Turn exam gating on for courses created before the default changed."""
NEW_DEFAULT = 80


def migrate(cr, version):
    cr.execute("""
        UPDATE slide_channel
           SET exam_unlock_completion = %s
         WHERE exam_unlock_completion = 0
    """, (NEW_DEFAULT,))
