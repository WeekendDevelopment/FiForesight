-- Feature 9 follow-up: enforce rule-owner consistency on alert_fires.
--
-- Adds a composite unique constraint on alert_rules(id, user_id) and a matching
-- composite foreign key on alert_fires(rule_id, user_id) so the DB guarantees
-- that a fire row always references a rule belonging to the same user.
-- This prevents a user-scoped insert from pairing a rule_id with a different owner.
--
-- Safe to run idempotently (IF NOT EXISTS / OR REPLACE).

alter table public.alert_rules
  add constraint if not exists alert_rules_id_user_unique
  unique (id, user_id);

alter table public.alert_fires
  drop constraint if exists alert_fires_rule_owner_fk;

-- Drop the existing single-column FK so we can replace it with the composite one.
alter table public.alert_fires
  drop constraint if exists alert_fires_rule_id_fkey;

alter table public.alert_fires
  add constraint alert_fires_rule_owner_fk
  foreign key (rule_id, user_id)
  references public.alert_rules(id, user_id)
  on delete cascade;
