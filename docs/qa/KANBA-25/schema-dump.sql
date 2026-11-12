--
-- PostgreSQL database dump
--

\restrict OqPHOktPc9hUQiR6J1zIuQhLjyRJzqGnCph5Mz5GQYaS5z3gRJq5NjlLdtnQc01

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg12+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg12+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: kb_harness; Type: SCHEMA; Schema: -; Owner: kanban_test
--

CREATE SCHEMA kb_harness;


ALTER SCHEMA kb_harness OWNER TO kanban_test;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: probe; Type: TABLE; Schema: kb_harness; Owner: kanban_test
--

CREATE TABLE kb_harness.probe (
    id bigint NOT NULL,
    note text NOT NULL
);


ALTER TABLE kb_harness.probe OWNER TO kanban_test;

--
-- Name: probe_id_seq; Type: SEQUENCE; Schema: kb_harness; Owner: kanban_test
--

ALTER TABLE kb_harness.probe ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME kb_harness.probe_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: probe probe_pkey; Type: CONSTRAINT; Schema: kb_harness; Owner: kanban_test
--

ALTER TABLE ONLY kb_harness.probe
    ADD CONSTRAINT probe_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict OqPHOktPc9hUQiR6J1zIuQhLjyRJzqGnCph5Mz5GQYaS5z3gRJq5NjlLdtnQc01

