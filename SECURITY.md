# Security

This project is a **read-only** IRCTC chart analyser. It must never book, pay,
solve captchas, or submit a reservation.

## Report a vulnerability

Email the maintainer privately. Do not open a public issue that includes
cookies, tokens, Chrome profiles, or passenger data.

## Hard rules

- Live HTTP/CDP clients may call only the three verified read paths listed in
  `app/forbidden.py`.
- Booking and payment path fragments are rejected in code.
- Cookie files and `.env` are gitignored. Never commit them.
- Logs redact `cookie`, `authorization`, `token`, `password`, and related keys.

## Running live reads

Charts Chrome is started on a private Xvfb display. Do not point `CHROME_CDP`
at a signed-in personal Chrome profile that you intend to publish or share.
The default profile directory is `~/.vacant-seat-finder-profile` and is not
part of this repository.
