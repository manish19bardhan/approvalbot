# Premium Channel Bot — Join Request Gate

User taps "Request to Join" on your private channel → bot DMs "buy
membership" → pays with Stars → bot auto-approves → user gets in.

No invite links. Bot approves the join request directly.

## Setup

### 1. Private channel banao
- Telegram → New Channel → Private
- Channel Settings → **Approve new members** → ON
  (warna join requests aayenge hi nahi)

### 2. Channel invite link banao
- Channel → Manage → Invite Links → create one
- Yeh link user ko do (website, ad, jahan bhi)

### 3. Bot banao
- @BotFather → /newbot → token copy

### 4. Bot ko channel me admin banao
Required:
- Add Users (join requests approve karne ke liye)
- Ban Users (expiry pe kick)
- Invite Users via Link

### 5. Channel ID pata karo
- Channel ka message @userinfobot pe forward → -100...

### 6. Configure