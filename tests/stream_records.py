"""DynamoDB stream records shaped like the notifier receives them."""


def stream_record(before, after, desk):
    analysis = {"M": {"desk": {"S": desk}}} if desk else None
    new = {
        "entity": {"S": "disruption"},
        "status": {"S": after},
        "disruption_id": {"S": "r-sick1042"},
        "report": {"M": {"type": {"S": "crew_unavailable"}}},
        **({"analysis": analysis} if analysis else {}),
    }
    return {
        "eventName": "MODIFY",
        "dynamodb": {"NewImage": new, "OldImage": {"status": {"S": before}}, "SequenceNumber": "1"},
    }
