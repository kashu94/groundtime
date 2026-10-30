"""The single DynamoDB table: attribute names and key layout.

Everything Groundtime keeps lives in one table: who may sign in, what people booked and
love, the delays customer care records, and Qloo's answers for a day. The flights and crew
trips are not here; they are the network (``crewops.network``), loaded from the bundled seed.
The infrastructure stack and the code that reads the table import these names, so the two
cannot drift apart.

Key layout (``PREFIX#value``):

==============================  =========================
Item                            pk / sk
==============================  =========================
User profile                    USER#username / PROFILE
Traveller's booking             BOOKING / TR-id
Traveller taste profile         TRAVELLER#TR-id / TASTE
Crew taste profile (opt-in)     CREW#C-id / TASTE
Delay on a flight               DELAY / flight-id
Qloo answer, cached a day       QLOO / request-hash
==============================  =========================

Bookings and delays each sit in one partition, so customer care reads all of them with one
query. There are a few hundred at most at this size.
"""

from __future__ import annotations

PK = "pk"
SK = "sk"
TTL = "expires_at"
"""Epoch seconds. Items with this attribute are deleted by DynamoDB after that time."""

SEPARATOR = "#"
