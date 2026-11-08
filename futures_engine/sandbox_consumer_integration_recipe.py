"""Explicit integration patch for the EC2-local sandbox_research_consumer.

The service file is not tracked in this repository. This file is an
auditable integration recipe, not an auto-deployment script.
"""

# Add next to existing imports:
# from futures_engine.sandbox_rejection_integration import handle_failed_message

# Replace the current except block (lines 67-72) with:
#
#         except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
#             print(json.dumps({"rejected_message_id": message.get("MessageId"),
#                               "reason": str(exc)}))
#             results["rejected"] += 1
#             # Known terminal failures: durable audit then delete.
#             # Unknown failures: retain for retry / existing DLQ policy.
#             handle_failed_message(sqs=sqs, queue_url=QUEUE,
#                                   message=message, exc=exc)
#             continue
#
# Keep the original successful-message deletion at line 73 unchanged.
# IMPORTANT: deploy only after CI, local backup, audit DB permissions,
# and an isolated mock-SQS smoke test. Do not replay the DLQ.
#
# WARNING: The real consumer's full file is not yet reviewed. Confirm that
# its exception handler does not also capture persistence failures and that
# the configured queue is signalpilot-signals-sandbox before applying.
