-- Migration: p1_16_link_purger (down)
-- Drops purge_invalid_object_links function and object_links_flagged_delete_guard_bd trigger

DROP TRIGGER IF EXISTS object_links_flagged_delete_guard_bd_trg ON object_links;
DROP FUNCTION IF EXISTS object_links_flagged_delete_guard_bd();
DROP FUNCTION IF EXISTS purge_invalid_object_links(uuid[], uuid, text);
