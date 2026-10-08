CREATE TABLE public.sales_inquiries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 name text NOT NULL CHECK (length(name) BETWEEN 2 AND 120),
 company text NOT NULL DEFAULT '',
 email text NOT NULL CHECK (length(email) <= 254),
 plan_code text REFERENCES public.plan_catalog(code),
 message text NOT NULL DEFAULT '' CHECK (length(message) <= 2000),
 consent_at timestamptz NOT NULL DEFAULT now(),
 status text NOT NULL DEFAULT 'new' CHECK (status IN ('new','contacted','converted','closed')),
 ip_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.sales_inquiries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.sales_inquiries FROM anon;
GRANT SELECT,UPDATE ON public.sales_inquiries TO authenticated;
CREATE POLICY sales_inquiries_owner_read ON public.sales_inquiries FOR SELECT TO authenticated USING (private.is_platform_admin());
CREATE POLICY sales_inquiries_owner_update ON public.sales_inquiries FOR UPDATE TO authenticated USING (private.is_platform_admin()) WITH CHECK (private.is_platform_admin());
CREATE INDEX sales_inquiries_created_idx ON public.sales_inquiries(created_at);
CREATE INDEX sales_inquiries_email_created_idx ON public.sales_inquiries(email,created_at);
CREATE INDEX sales_inquiries_ip_created_idx ON public.sales_inquiries(ip_hash,created_at);
