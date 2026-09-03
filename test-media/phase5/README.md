# Phase 5 controlled checks

Use the Expo harness only to generate local continuous traffic and observe raw
freshness/recovery state.

1. Start the backend and Expo harness on the same private network.
2. Select **Start continuous test** and confirm frame IDs increase, results stay
   within `max_result_age_ms`, and the camera preview remains responsive.
3. Temporarily interrupt the phone-to-laptop private-network connection without
   stopping either process. Confirm one `Connection lost` state, subsequent
   quiet retry states, and no retained overlay or guidance.
4. Restore the same connection. Confirm the existing session resumes with a
   `Local backend connection recovered` state and fresh overlays return.
5. Select **Stop continuous test** and confirm no further frames arrive.

Keep the scene controlled and remain sighted. Do not conduct a blindfolded or
roadway test.
