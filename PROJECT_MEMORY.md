# PROJECT_MEMORY.md

## 1. Project Identity

Project name: Unknown / needs inspection  
Project type: Telegram Bot / Mini App / Website / Backend / Other  
Main purpose: Unknown / needs inspection  
Target users: Unknown / needs inspection  
Current status: Unknown / needs inspection  

Short description:
- This project is built to: Unknown / needs inspection
- Main user problem: Unknown / needs inspection
- Main business goal: Unknown / needs inspection

---

## 2. Core Architecture

Frontend:
- Unknown / needs inspection

Backend:
- Unknown / needs inspection

Database:
- Unknown / needs inspection

Hosting:
- Unknown / needs inspection

Bot framework:
- Unknown / needs inspection

AI provider/model:
- Unknown / needs inspection

Payment system:
- Unknown / needs inspection

External services:
- Unknown / needs inspection

---

## 3. Important Project Rules

- Do not redesign the whole architecture without explicit request.
- Do not remove working logic unless there is a clear reason.
- Make minimal safe changes.
- Keep user/payment/subscription logic stable.
- If database schema changes, document the migration.
- If environment variables change, update `.env.example`.
- Never write secrets, API keys, tokens, passwords, or private URLs in this file.
- Before changing payment, subscription, or access logic, check the current flow first.
- If something is unclear, inspect the code first instead of guessing.

---

## 4. Memory Update Policy

This file is NOT a daily diary and must NOT become a dump of every small change.

Only update this file when the change is important for future AI assistants to understand, debug, or safely continue the project.

Update this file only for:
- Architecture changes
- Database schema changes
- Payment logic changes
- Subscription logic changes
- User access logic changes
- Important user flow changes
- Deployment or environment changes
- AI prompt behavior changes
- Course or lesson logic changes
- Important business logic decisions
- Major bug fixes
- Security-sensitive changes

Do NOT update this file for:
- Small text edits
- Emoji changes
- Typo fixes
- Minor UI/CSS changes
- Console log cleanup
- Small refactoring with no logic change
- Temporary experiments
- Changes already obvious from the code

Before updating memory, ask internally:

> Will this help another AI assistant understand, debug, or safely continue this project later?

If the answer is no, do not update this file.

When updating memory, keep it short and useful:
- What changed
- Why it changed
- Files touched
- Risk / follow-up if needed

Never turn this file into a long changelog.

---

## 5. Key Files and Folders

Main files:
- `main.py` — Unknown / needs inspection
- `bot.py` — Unknown / needs inspection
- `database.py` — Unknown / needs inspection
- `config.py` — Unknown / needs inspection
- `handlers/` — Unknown / needs inspection
- `keyboards/` — Unknown / needs inspection
- `services/` — Unknown / needs inspection
- `miniapp/` — Unknown / needs inspection
- `.env.example` — Unknown / needs inspection

Important note:
- Do not rename or delete important files unless necessary.

---

## 6. Database Schema Summary

### users
Purpose: stores Telegram users and access status.

Important fields:
- `telegram_id`
- `language`
- `status`
- `payment_status`
- `subscription_until`
- `question_limit`
- `questions_used`

### payments
Purpose: stores payment requests and confirmations.

Important fields:
- `payment_id`
- `telegram_id`
- `amount`
- `payment_code`
- `status`
- `created_at`
- `confirmed_at`

### logs / history
Purpose: stores important user actions or AI interactions.

Important fields:
- Unknown / needs inspection

---

## 7. Current Business Logic

### User onboarding
Current flow:
1. Unknown / needs inspection

### Subscription logic
Current logic:
- Free trial: Unknown / needs inspection
- Paid plans: Unknown / needs inspection
- Question limits: Unknown / needs inspection
- Expiration logic: Unknown / needs inspection
- Access blocked when: Unknown / needs inspection

### Payment logic
Current logic:
- Payment method: Unknown / needs inspection
- Manual approval: Unknown / needs inspection
- Auto approval: Unknown / needs inspection
- Admin notification: Unknown / needs inspection

### AI logic
Current logic:
- Unknown / needs inspection

---

## 8. Current Features

Working:
- Unknown / needs inspection

Partially working:
- Unknown / needs inspection

Not built yet:
- Unknown / needs inspection

---

## 9. Important Decisions

### Decision 1
Date: Unknown  
Decision: Unknown / needs inspection  
Reason: Unknown / needs inspection  
Risk: Unknown / needs inspection  

---

## 10. Recent Important Changes

### 2026-06-07 — Course table migration bootstrap

Changed:
- Added an Alembic migration after `0010` that creates `course_lessons`, `course_progress`, and `course_attempts` before later course workflow migrations alter them.

Why:
- Fresh Railway Postgres databases were failing deploy at `0011_add_course_workflow_fields` because `course_progress` did not exist yet.

Files touched:
- `alembic/versions/0010a_create_course_tables.py`
- `alembic/versions/0011_add_course_workflow_fields.py`

Risk:
- Existing databases already at head will not rerun this inserted migration. Fresh or partially failed databases at `0010` can continue to `head`.

Follow-up:
- Redeploy Railway web service and confirm `alembic upgrade head` reaches `0035_partner_payout_safety`.

### 2026-06-06 — Feedback limit discount offer

Changed:
- Bot feedback dislike option `limits` now schedules the same 5-minute 20% subscription discount offer as `price`.
- The limits offer uses a separate user-facing message about bot limits, but reuses the existing feedback discount checkout/payment flow.

Why:
- Users who say bot limits are too low should get the same conversion path as users who say subscription price is high.

Files touched:
- `app/repositories/bot_feedback_repo.py`
- `app/services/bot_feedback_service.py`
- `app/services/discount_service.py`
- `app/bot/utils/i18n.py`

Risk:
- Existing DB fields are reused; no migration. Scheduler still sends due offers from the existing 60-second background loop.

Follow-up:
- Smoke test in Telegram: choose `Limitlar kam`, wait 5 minutes, open the 20% discount flow, and submit a payment screenshot.

### 2026-06-06 — Image caption as AI command

Changed:
- Photo messages now pass Telegram caption text into the image AI flow.
- The image explainer treats caption text as the user's command and uses analyzer output as the image source context.
- Image file IDs are excluded from normal QA chat history; follow-up context should come from stored image context.
- QA AI history now keeps system context messages, so stored image context is available in follow-up questions.

Why:
- Users sending photo + text like "Tarjima qil" need the bot to follow the text instruction instead of only explaining the image.

Files touched:
- `app/bot/handlers/messages.py`
- `app/services/image_qa_service.py`
- `app/services/image_explainer_service.py`
- `app/services/qa_service.py`
- `app/services/ai_service.py`

Risk:
- Prompt-only behavior change; image limits, subscription access, and payment logic are unchanged.

Follow-up:
- Test in Telegram with a photo caption command such as "Tarjima qil".

### 2026-06-05 — Command/menu input cleanup

Changed:
- Private-chat slash commands and main/course reply menu button messages are deleted after their handlers run.

Why:
- Keep Telegram chats clean while preserving command behavior.

Files touched:
- `app/bot/middlewares/cleanup.py`
- `app/bot/create_bot.py`

Risk:
- Delete failures are ignored; group chats are not affected.

Follow-up:
- Verify on production bot that Telegram allows deleting incoming private-chat command messages.

### 2026-06-04 — Localized TJS card subscription blocks

Changed:
- Card/TJS subscription selection and checkout messages now keep one compact format while matching the user's language (TJ/RU/UZ).
- TJS plan prices show `💸 {amount} TJS 🇹🇯` in the plan list and `{amount} TJS 💸` in checkout.
- Alipay/WeChat QR payment flow remains separate.

Why:
- Avoid mixed-language payment instructions and keep card payment instructions easy to read.

Files touched:
- `app/bot/handlers/subscription.py`

Risk:
- Text-only card flow change; payment amount and subscription logic unchanged.

Follow-up:
- Verify rendered Telegram blockquote spacing on production bot after deploy.

### 2026-05-25 — Course narrative text formatting

Changed:
- Course text blocks with narrator-style lines (`旁白` / no speaker) now render as text instead of dialogue: bold Chinese line, pinyin below, translation below.
- Narrative blocks show `Matn/Текст/Матн` in the course message header instead of `Dialog`.

Why:
- Textbook passages without speakers were hard to read when formatted like dialogue lines.

Files touched:
- `app/bot/utils/course_formatter.py`

Risk:
- This is display-only; stored lesson JSON and progress logic are unchanged.

### 2026-05-25 — Referral trial active access

Changed:
- Users can unlock 3 days of non-paid `active` access after collecting 10 active referrals.
- This reward is separate from the existing referral bonus and referral discount flows: +5 bonus questions and 3-referral discount counters still use their existing fields.
- Referral active access does not set `payment_status=approved`; it creates a fixed $2 AI usage budget for the trial active window.
- In trial active, text/course/photo use the fixed $2 AI budget; photo no longer has a separate daily image limit during this reward window.
- If the fixed $2 AI budget is depleted before 3 days, the non-paid active user is downgraded back to `trial`; if 3 days expire first, the user is also downgraded even if budget remains.
- Voice is restricted to real paid subscribers (`status=active` and `payment_status=approved`); non-paid active windows do not unlock voice.
- Profile labels non-paid active as `Sinov muddati`, shows only referral count, and leaves the subscription line empty unless the user has a real paid subscription.
- A new `users.referral_trial_count_started_at` marker resets this feature's referral count after each 3-day reward window.

Why:
- Trial users need a referral path to temporarily become `active` without replacing a real paid subscription.

Files touched:
- `app/services/referral_service.py`
- `app/services/access_service.py`
- `app/services/ai_usage_budget_service.py`
- `app/services/qa_service.py`
- `app/services/image_qa_service.py`
- `app/services/course_miniapp_result_service.py`
- `app/repositories/referral_repo.py`
- `app/db/models/user.py`
- `app/db/session.py`
- `app/bot/handlers/messages.py`
- `app/bot/handlers/referral.py`
- `app/bot/handlers/commands.py`
- `app/bot/handlers/menu.py`
- `app/bot/keyboards/referral.py`
- `app/bot/utils/i18n.py`
- `alembic/versions/0028_referral_trial_activation.py`

Risk:
- Paid users are still identified only by `payment_status=approved`; do not treat `status=active` alone as paid subscription.

Follow-up:
- Run DB migration in deploy environments before relying on referral trial progress display.

### 2026-05-25 — Referral bonus usage is lifetime

Changed:
- Daily trial limit reset now resets only `questions_used`; it does not reset `bonus_questions_used`.
- Referral trial active activation also keeps already-used referral bonus questions spent.

Why:
- Referral +5 questions are a one-time bonus, not a daily renewed allowance.

Files touched:
- `app/services/access_service.py`
- `app/services/referral_service.py`

Risk:
- Users who already reused bonus questions before this fix are not retroactively corrected.

Follow-up:
- If historical correction is required, add a separate data audit instead of mixing it into runtime access logic.

### 2026-05-24 — Dynamic course dialogue audio admin

Changed:
- Admin audio panel now builds required audio types from each lesson's current `dialogue_json` block count, so HSK4 lessons with 5 dialogues show `vocab` plus `dialogue_1` through `dialogue_5`.
- Audio status now distinguishes complete, partial, and missing lessons, and ignores obsolete audio types that no longer match the current lesson format.
- Course audio playback no longer falls back from `dialogue_2+` to `dialogue_1`; missing dialogue-specific audio now stays unavailable instead of playing the wrong old audio.

Why:
- After lessons were split into more dialogue blocks, the old admin/audio logic could hide later dialogues or reuse outdated audio under the wrong dialogue.

Files touched:
- `app/bot/handlers/admin_audio.py`
- `app/bot/handlers/course.py`
- `app/repositories/course_audio_repo.py`
- `app/services/course_engine_service.py`
- `app/services/course_tutor_service.py`

Risk:
- Existing lessons that only have `dialogue_1` uploaded will show missing audio for later dialogue blocks until admin uploads each specific dialogue audio.

Follow-up:
- If obsolete DB audio should be deleted automatically, add an explicit admin cleanup action instead of silently deleting rows.

### 2026-05-24 — HSK4 upper lesson localization quality

Changed:
- HSK4 上 lessons 1-3 now keep PDF-canonical Chinese dialogue/new-word material while adding Uzbek, Russian, and Tajik translations, dialogue pinyin, localized grammar explanations, and localized mini quiz/homework prompts.
- The HSK4 static mini app fallback data now uses language-aware vocabulary, grammar, and quiz strings instead of Uzbek-only strings.

Why:
- Bot course messages and Mini App could show blank or Uzbek-only explanations for Russian/Tajik users because HSK4 seed payload only contained Uzbek fields and empty dialogue pinyin.

Files touched:
- `scripts/hsk4_upper_pdf_materials.py`
- `scripts/hsk4_upper_i18n.py`
- `scripts/verify_hsk4_upper_pdf_materials.py`
- `app/static/hsk4.html`

Risk:
- Dialogue/new words remain source-locked to the textbook data in `scripts/hsk4_upper_pdf_materials.py`; only translations/explanations/pinyin are added in the i18n layer.

Follow-up:
- Use the same localization verifier before enabling HSK4 上 lessons 4-6 in Mini App support.

### 2026-05-24 — Course level completion upgrade flow

Changed:
- When a user finishes the last lesson in a HSK level, the bot now sends a level-completion congratulations message with lesson, vocabulary, dialogue, and study-duration progress.
- The bot then asks whether to move to the next HSK level in Uzbek, Russian, and Tajik. Yes upgrades `users.level`, resets course progress for the next level, and opens lesson 1. No keeps the user on the completed level and shows that level's lesson list.
- Final lessons are now marked completed only once, preventing repeated "next lesson" presses from double-counting progress.

Why:
- The previous final-lesson path only showed a generic "lesson completed" message when no next lesson existed.

Files touched:
- `app/services/course_engine_service.py`
- `app/bot/handlers/course.py`
- `app/bot/handlers/messages.py`
- `app/bot/keyboards/course_context.py`
- `app/bot/utils/i18n.py`

Risk:
- Advancing to the next level resets `CourseProgress.completed_lessons_count` for the new level because the current schema stores one course progress row per user.

Follow-up:
- If global cross-level progress is required later, add a dedicated course completion history table instead of overloading the current per-user progress row.

### 2026-05-24 — Course block AI context

Changed:
- HSK course AI prompts now receive block-level course context for block lessons: dialogue block, block vocabulary, grammar points, mini quiz, and mini homework.
- HSK3 lessons 13-16 were wired through `scripts/hsk3_pdf_materials.py`, so dialogue/new words are PDF canonical instead of synthetic seed content.

Why:
- Mini App quiz/homework review must explain the exact user mistakes using the same block material shown in the course.

Files touched:
- `app/services/course_tutor_service.py`

### 2026-05-24 — HSK3 block lesson completion

Changed:
- HSK3 lessons 17-20 now use PDF canonical dialogue/new-word material through `scripts/hsk3_pdf_materials.py`.
- All HSK3 lessons 1-20 now generate per-dialogue block steps with `block_vocab_N` before `dialogue_N`.

Why:
- Lessons 17-20 were still in the older V2 format, so later parts could start directly with `dialogue_3`/`dialogue_4` and skip the new-word section.

Files touched:
- `scripts/hsk3_pdf_materials.py`
- `scripts/seed_hsk3_lesson_17.py`
- `scripts/seed_hsk3_lesson_18.py`
- `scripts/seed_hsk3_lesson_19.py`
- `scripts/seed_hsk3_lesson_20.py`
- `scripts/verify_hsk3_pdf_materials.py`

Risk:
- Database must run the course seed sync or app restart so existing stored lesson JSON is refreshed.

Follow-up:
- If a deployed bot still shows old HSK3 lesson flow, restart/reseed first before debugging UI step logic.

### 2026-05-24 — Block grammar de-duplication

Changed:
- HSK1, HSK2, and HSK3 block lessons now normalize grammar per lesson so the same book grammar number is not shown repeatedly across multiple blocks.
- Every block still gets a short context grammar note based on the actual dialogue sentence used in that block.
- Telegram formatter and Mini App lesson payload prefer block `grammar_notes` over long book grammar items to avoid duplicate-looking explanations.

Why:
- Users saw repeated grammar material across blocks and some blocks felt like they had no useful grammar.

Files touched:
- `scripts/block_context_grammar.py`
- `scripts/hsk1_block_metadata.py`
- `scripts/hsk2_block_metadata.py`
- `scripts/hsk3_pdf_materials.py`
- `app/bot/utils/course_formatter.py`
- `app/services/course_miniapp_lesson_service.py`
- `app/services/course_tutor_service.py`
- `scripts/verify_course_block_grammar.py`

Risk:
- Existing database lesson JSON must be refreshed by seed sync/app restart before deployed users see the normalized grammar.
- `app/services/course_miniapp_result_service.py`
- `scripts/hsk3_pdf_materials.py`
- `scripts/seed_hsk3_lesson_13.py` to `scripts/seed_hsk3_lesson_16.py`
- `scripts/verify_hsk3_pdf_materials.py`

Why:
- 

Files touched:
- 

Risk:
- 

Follow-up:
- 

### 2026-05-24 — HSK4 上 first 3 lessons block format

Changed:
- HSK4 上 lessons 1-3 now use PDF-derived dialogue and vocabulary material through `scripts/hsk4_upper_pdf_materials.py`.
- Each of those lessons has 5 dialogue blocks, per-block vocabulary, one relevant PDF grammar point, mini quiz, and mini homework.
- HSK4 Mini App support is enabled only for lessons 1-3 for now via `hsk4.html`.

Why:
- HSK4 upper lessons had fewer dialogue blocks than the PDF and some lesson 2/3 grammar/vocabulary was from the wrong older seed format.

Files touched:
- `scripts/hsk4_upper_pdf_materials.py`
- `scripts/seed_hsk4_lesson_01.py` to `scripts/seed_hsk4_lesson_03.py`
- `app/bot/utils/course_miniapp.py`
- `app/static/hsk4.html`

Risk:
- Lessons 4+ are intentionally not enabled in HSK4 Mini App yet; continue in small batches to avoid content errors.

### 2026-05-24 — HSK4 上 lessons 4-6 PDF alignment

Changed:
- HSK4 上 lessons 4-6 now use canonical textbook dialogue/new-word data through `scripts/hsk4_upper_pdf_materials_4_6.py`.
- Each lesson has 5 dialogue blocks, 31 textbook vocabulary items, 5 grammar points, three-language translations, pinyin, per-block mini quiz/homework, and Mini App fallback data.
- Seed files for lessons 4-6 are now thin wrappers so stale non-PDF fallback content cannot leak into runtime data.

Why:
- Lessons 4-6 previously still contained older non-canonical seed material and HSK4 Mini App fallback only covered lessons 1-3.

Files touched:
- `scripts/hsk4_upper_pdf_materials.py`
- `scripts/hsk4_upper_pdf_materials_4_6.py`
- `scripts/seed_hsk4_lesson_04.py` to `scripts/seed_hsk4_lesson_06.py`
- `scripts/verify_hsk4_upper_pdf_materials.py`
- `app/static/hsk4.html`

Risk:
- Database must be reseeded for deployed environments; local DB was updated for HSK4-L04, HSK4-L05, and HSK4-L06 in this session.

### 2026-05-25 — HSK4 上 lessons 7-10 PDF alignment

Changed:
- HSK4 上 lessons 7-10 now use canonical textbook dialogue/new-word data through `scripts/hsk4_upper_pdf_materials_7_10.py`.
- Each lesson has 5 dialogue blocks, per-block vocabulary, one relevant grammar point, three-language translations, pinyin, mini quiz, and mini homework.
- HSK4 static Mini App fallback data now covers lessons 1-10 with grammar-focused quiz questions and no fill-blank style quiz items.

Why:
- Lessons 7-10 still had stale seed JSON and Mini App coverage stopped at lesson 6.

Files touched:
- `scripts/hsk4_upper_pdf_materials.py`
- `scripts/hsk4_upper_pdf_materials_7_10.py`
- `scripts/seed_hsk4_lesson_07.py` to `scripts/seed_hsk4_lesson_10.py`
- `scripts/verify_hsk4_upper_pdf_materials.py`
- `app/static/hsk4.html`

Risk:
- Database must be reseeded for deployed environments; local DB was updated for HSK4-L07 through HSK4-L10 in this session.

### 2026-05-25 — HSK4 下 lessons 11-13 PDF alignment

Changed:
- HSK4 下 lessons 11-13 now use canonical textbook dialogue/new-word data through `scripts/hsk4_lower_pdf_materials.py`.
- Each lesson has 5 blocks, per-block vocabulary, relevant grammar, pinyin, three-language translations, mini quiz, and mini homework.
- HSK4 static Mini App fallback now recognizes lessons 1-13 and includes grammar quiz items for lessons 11-13.

Why:
- HSK4 下 needed to start from the textbook format; older lower seed data had incomplete lesson blocks and stale lesson 11 content.

Files touched:
- `scripts/hsk4_lower_pdf_materials.py`
- `scripts/hsk4_lower_seed_data.py`
- `scripts/seed_hsk4_lesson_11.py`
- `scripts/verify_hsk4_lower_pdf_materials.py`
- `app/static/hsk4.html`

Risk:
- Database must be reseeded for deployed environments; local DB was updated for HSK4-L11 through HSK4-L13 in this session.

### 2026-05-25 — HSK4 Mini App support range

Changed:
- HSK4 Mini App support range is now lessons 1-13.

Why:
- HSK4 上 lessons 4-10 had Mini App content and API payloads, but course buttons were blocked by the stale supported range `1-3`.

Files touched:
- `app/bot/utils/course_miniapp.py`

Risk:
- HSK4 lessons beyond 13 stay unsupported until their lesson data is converted.

### 2026-05-25 — HSK4 下 lessons 14-16 PDF alignment

Changed:
- HSK4 下 lessons 14-16 now use canonical textbook dialogue/new-word data through `scripts/hsk4_lower_pdf_materials_14_16.py`.
- Each lesson has 5 blocks, per-block vocabulary, relevant grammar, pinyin, three-language translations, mini quiz, and mini homework generated through the lower seed pipeline.
- HSK4 static Mini App fallback and support range now cover lessons 1-16 with grammar-focused quiz items and no blank-fill quiz format.

Why:
- Lessons 14-16 needed the same PDF-based format as lessons 11-13 before continuing HSK4 下 in small batches.

Files touched:
- `scripts/hsk4_lower_pdf_materials.py`
- `scripts/hsk4_lower_pdf_materials_14_16.py`
- `scripts/verify_hsk4_lower_pdf_materials.py`
- `app/bot/utils/course_miniapp.py`
- `app/static/hsk4.html`

Risk:
- Runtime database must be reseeded or app restarted in deployed environments before Telegram course messages show HSK4-L14 through HSK4-L16.

### 2026-05-28 — HSK4 下 lessons 17-20 PDF alignment

Changed:
- HSK4 下 lessons 17-20 now use canonical textbook dialogue/new-word data through `scripts/hsk4_lower_pdf_materials_17_20.py`.
- Each lesson has 5 blocks, per-block vocabulary, relevant grammar, pinyin, three-language translations, mini quiz, and mini homework generated through the lower seed pipeline.
- HSK4 static Mini App fallback and support range now cover lessons 1-20 with grammar-focused quiz items and no blank-fill quiz format.

Why:
- Lessons 17-20 complete HSK4 下 in the same PDF-based format as lessons 11-16.

Files touched:
- `scripts/hsk4_lower_pdf_materials.py`
- `scripts/hsk4_lower_pdf_materials_17_20.py`
- `scripts/verify_hsk4_lower_pdf_materials.py`
- `app/bot/utils/course_miniapp.py`
- `app/static/hsk4.html`

Risk:
- Runtime database must be reseeded or app restarted in deployed environments before Telegram course messages show HSK4-L17 through HSK4-L20.

### 2026-06-04 — Localized admin messaging and TJS card subscriptions

Changed:
- Admin broadcast and ad campaign text can be written once in Tajik, then localized to TJ/UZ/RU through AI before sending; users receive the variant matching their language.
- Broadcast and ad campaign confirm flows include an admin test send without clearing the prepared message.
- Visa/Card subscription pricing is TJS-only: 10 days = 29 TJS, 1 month = 89 TJS by default. Alipay/WeChat remain in yuan.
- Stale checkout drafts are recalculated when a screenshot arrives so old USD drafts do not survive after the TJS switch.
- Expired admin/feedback discount buttons edit the original offer message to an expired text instead of only showing an alert.

Why:
- Admins should not send separate messages per language, and card subscription revenue should be priced in somoni.

Files touched:
- `app/services/broadcast_translation_service.py`
- `app/bot/handlers/admin_broadcast.py`
- `app/bot/handlers/admin_ads.py`
- `app/services/ad_campaign_service.py`
- `app/services/subscription_price_service.py`
- `app/bot/handlers/subscription.py`
- `app/services/payment_service.py`

Risk:
- Broadcast/ad translations depend on `OPENAI_API_KEY`; if translation fails, the Tajik source is used as a safe fallback.
- Telegram bot updates do not expose user IP, so non-TJ card users see a general bank-rate TJS payment note instead of IP-based country detection.

---

## 11. Known Problems

### Problem 1
Problem:
- Unknown / needs inspection

Suspected cause:
- Unknown / needs inspection

Status:
- Open / Fixed / Needs testing

---

## 12. Next Planned Work

Priority 1:
- Unknown / needs inspection

Priority 2:
- Unknown / needs inspection

Priority 3:
- Unknown / needs inspection

---

## 13. Required Environment Variables

Do not write real values here.

Required:
- `BOT_TOKEN`
- `DATABASE_URL`
- `OPENAI_API_KEY`
- `ADMIN_IDS`

Optional:
- Unknown / needs inspection

---

## 14. AI Assistant Instructions

Any AI coding assistant working on this project must:

1. Read this file before changing code.
2. Understand the current architecture before editing.
3. Make minimal changes.
4. Preserve working flows.
5. Never store secrets in this file.
6. Update this file only after important changes.
7. Do not write small cosmetic changes here.
8. If changing database/payment/subscription logic, explain the risk.
9. If unsure, inspect the code before guessing.
10. Do not rewrite this file completely unless explicitly requested.
