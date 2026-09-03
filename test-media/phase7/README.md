# Phase 7 physical OCR check

Use a printed or laptop-displayed sign with large, high-contrast English text and
at least one route token, for example `BUS 42A CENTRAL`.

1. Start the local backend and Expo test harness on the same private LAN.
2. Confirm `/api/v1/health` reports the `ocr` module as `READY`.
3. Open the camera test, fill most of the preview with the prepared sign, and tap
   **Read sign once**.
4. Confirm the response contains the visible text and route `42A`.
5. Repeat with partially obscured or poorly lit text and confirm uncertain text is
   labeled `LOW`, or a blank scene returns `No text found.`.
6. While one OCR request is active, confirm Walk session creation and analysis
   remain responsive. A second Explore request may return retryable `CONFLICT`.

The harness shows raw backend output only. It does not implement production
Explore UX or speech, and the submitted image must not appear in `data/`.
