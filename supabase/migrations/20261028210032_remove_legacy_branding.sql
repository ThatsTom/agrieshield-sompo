-- Atualiza instalações existentes para as opções neutras de seguradora.
begin;

update public.agrishield_maquinarios
set seguradora = 'OUTRA', seguradora_outro = 'Não informada'
where seguradora is not null
  and seguradora not in ('MAPFRE', 'PORTO_SEGURO', 'ALLIANZ', 'OUTRA');

alter table public.agrishield_maquinarios
  drop constraint if exists agrishield_maquinarios_seguradora_check;

alter table public.agrishield_maquinarios
  add constraint agrishield_maquinarios_seguradora_check
  check (seguradora is null or seguradora in (
    'MAPFRE', 'PORTO_SEGURO', 'ALLIANZ', 'OUTRA'
  ));

commit;
