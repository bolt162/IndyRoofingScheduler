"""
Build queue customer emails.

Weekly Thursday update, welcome on queue entry, reschedule emails, and the
internal second-reschedule alert. Copy lives in copy.py and is the approved
"Build Queue Weekly Email Cadence" text; logic lives in selector.py.

Nothing sends unless EMAIL_MODE is "test" or "live" (default "off").
"""
