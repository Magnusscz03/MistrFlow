GRANT SELECT (code,name,description,monthly_cents,annual_cents,currency,is_public,is_recommended,active,sort_order) ON public.plan_catalog TO anon;
CREATE POLICY plan_catalog_public_pricing ON public.plan_catalog FOR SELECT TO anon USING (active AND is_public);
