-- Data-only restore extracted from zarly_dump.sql
-- Safe to run on a fresh Django-migrated DB (schema already exists)
-- Run with: docker exec -i zarlyos-db psql -U postgres zarlyos < zarly_restore_data.sql

SET session_replication_role = replica; -- disable FK checks during import

COPY public.customers_product (id, name, price, description, stock, image) FROM stdin;
2	Keropok Ikan Kelantan	3.50		33	product_images/promo2.jpg
3	Kek Marble	15.00		4	product_images/promo1.jpg
1	Asam Botol Thai	10.00		92	product_images/promo1_WE8IKO2.jpg
\.

COPY public.customers_user (id, password, last_login, is_superuser, username, first_name, last_name, email, is_staff, is_active, date_joined, role, phone_number) FROM stdin;
8	pbkdf2_sha256$1200000$KWEwcybdfEKPTAiadSNQtC$RBBB6IMDnbkW1S4gB/hBja2boeZQLgGC+b5gxL6j9iE=	2026-04-08 16:13:58.853745+00	t	1			1@gmai.com	t	t	2026-04-08 16:13:33.830112+00	customer
4	pbkdf2_sha256$1200000$K1DKbVY1chog4P8wiHliW7$eSQUFMuyLMkF0BMt9MI5jojnKjUeEDryMNI9d+Xp9Mg=	\N	f	name	satu	dua	m22@mail.com	f	t	2026-01-11 10:11:28+00	customer	01111
1	pbkdf2_sha256$1200000$kuYFgCdHv5yuUadgMChIsv$eyIkMdyVHJxbEjyJfwTReuFm1rR7lgoYee5BUnXCFkk=	2026-01-12 06:40:43.650927+00	t	zarly_user			rusdirashid1401@gmail.com	t	t	2026-01-08 21:14:29.234626+00	customer
7	pbkdf2_sha256$1200000$Wrl1K2BENhR6f5n6ANpHon$t3757ng4w2otc6+TFhSt8DQyAaJawuGyyGbAFo5F2Ps=	2026-01-12 06:49:25.576207+00	f	atan			atan@mail.com	f	t	2026-01-12 06:48:57.392302+00	customer	01290129210
3	pbkdf2_sha256$1200000$wc4kRWL918Hoy3q7v0L0Au$0Ymw89/2AO6SinMl4grWu1IjqB2J7ScJVrg9KlfVDUo=	2026-01-15 04:24:09.742609+00	f	cust	maznah	hamid	m@mail.com	f	t	2026-01-11 09:23:25+00	customer	01111
2	pbkdf2_sha256$1200000$MOFdOYMMYeKpuboBEiqUsx$1Y1Ua4PtcccGVuaKyXG39veCIZoUNeA5fBcbtqG8AeE=	2026-01-15 04:30:07.693201+00	t	udi				t	t	2026-01-09 20:20:54+00	sales_admin
\.

COPY public.auth_group (id, name) FROM stdin;
1	customer
\.

COPY public.customers_user_groups (id, user_id, group_id) FROM stdin;
1	3	1
\.

COPY public.customers_user_user_permissions (id, user_id, permission_id) FROM stdin;
1	3	4
\.

COPY public.admins_order (id, total_amount, status, otp_code, created_at, approved_at, approved_by_id, customer_id, payment_proof) FROM stdin;
2	3.50	rejected	\N	2026-01-10 18:04:28.663099+00	\N	\N	2
1	46.00	pending_payment	\N	2026-01-10 18:03:35.323609+00	\N	\N	2
4	3.50	rejected	\N	2026-01-10 20:15:49.659135+00	\N	\N	2	payment_proofs/muiz_soc_events_mIofG1n.pdf
5	20.00	pending_payment	\N	2026-01-10 21:23:17.849543+00	\N	\N	2
6	15.00	approved	\N	2026-01-10 21:24:00.64461+00	2026-01-10 21:51:09.229945+00	2	2	payment_proofs/683004.jpg
8	3.50	approved	\N	2026-01-11 09:27:38.78408+00	2026-01-11 09:28:48.350958+00	2	2	payment_proofs/photo_2024-05-13_01-20-54.jpg
7	28.50	pending_payment	\N	2026-01-11 09:27:01.554661+00	\N	\N	2
9	7.00	pending	\N	2026-01-11 10:39:33.726261+00	\N	\N	3
10	10.00	pending	\N	2026-01-11 17:52:37.778821+00	\N	\N	3	payment_proofs/photo_2024-05-13_01-20-54_y8VNGKW.jpg
3	22.00	approved	\N	2026-01-10 20:11:34.622082+00	2026-01-11 18:00:28.989112+00	2	2	payment_proofs/muiz_soc_events.pdf
12	3.50	pending	\N	2026-01-11 18:28:17.632598+00	\N	\N	2
11	3.50	pending_payment	\N	2026-01-11 18:21:11.557061+00	\N	\N	3
13	15.00	approved	\N	2026-01-12 07:05:49.556323+00	2026-01-12 07:06:06.95082+00	2	3	payment_proofs/photo_2024-05-13_01-20-54_WWpH2YD.jpg
14	10.00	approved	\N	2026-01-12 07:36:32.267621+00	2026-01-12 07:37:09.653799+00	2	3	payment_proofs/683004_VywtGYM.jpg
15	3.50	pending_payment	\N	2026-01-12 07:37:57.340098+00	\N	\N	3
16	15.00	pending	\N	2026-01-12 08:23:25.180889+00	\N	\N	3
49	10.00	pending	\N	2026-01-15 04:25:06.172647+00	\N	\N	3
50	10.00	pending_payment	\N	2026-01-15 04:25:32.771669+00	\N	\N	3
\.

COPY public.admins_orderitem (id, quantity, subtotal, order_id, product_id) FROM stdin;
1	6	21.00	1	2
2	1	15.00	1	3
3	1	10.00	1	1
4	1	3.50	2	2
5	2	7.00	3	2
6	1	15.00	3	3
7	1	3.50	4	2
8	2	20.00	5	1
9	1	15.00	6	3
10	1	3.50	7	2
11	1	10.00	7	1
12	1	15.00	7	3
13	1	3.50	8	2
14	2	7.00	9	2
15	1	10.00	10	1
16	1	3.50	11	2
17	1	3.50	12	2
18	1	15.00	13	3
19	1	10.00	14	1
20	1	3.50	15	2
21	1	15.00	16	3
54	1	10.00	49	1
55	1	10.00	50	1
\.

COPY public.admins_digitalsignature (id, signature_hash, pdf_path, "timestamp", signature_value, order_id) FROM stdin;
1	71d13a914ac12c0aa8e536fcaffb4d338ca101559e1e9b8d15146a11aac97148	signed_pdfs\\signed_order_6.pdf	2026-01-10 21:51:09.188361+00		6
2	524c500d0c6fea8bc4fb970995a4064cbd89691ae1bb5e2b2a3eb73b2f885e63	signed_pdfs\\signed_order_8.pdf	2026-01-11 09:28:48.342221+00		8
3	01c6a502b258bb5c5a6d046c0e2819b28b6c92e73b4f63d4f086e11a7dc14b17	signed_pdfs\\signed_order_3.pdf	2026-01-11 18:00:28.958529+00		3
4	8c6f6c094e6f4c74230b327b35eef9fc027c19213527064113f3572f6e0b220d	signed_pdfs\\signed_order_13.pdf	2026-01-12 07:06:06.936655+00		13
5	e73c4ddafa6aa50a03b811151c765a6416c956fec89ba0b7840d79232e81ad1d	signed_pdfs\\signed_order_14.pdf	2026-01-12 07:37:09.637626+00		14
\.

-- Reset sequences so new inserts don't collide with restored IDs
SELECT setval('public.customers_product_id_seq', 3);
SELECT setval('public.customers_user_id_seq', 8);
SELECT setval('public.customers_user_groups_id_seq', 1);
SELECT setval('public.customers_user_user_permissions_id_seq', 1);
SELECT setval('public.auth_group_id_seq', 1);
SELECT setval('public.admins_order_id_seq', 50);
SELECT setval('public.admins_orderitem_id_seq', 55);
SELECT setval('public.admins_digitalsignature_id_seq', 5);

SET session_replication_role = DEFAULT; -- re-enable FK checks
