export type TipoParametroModelo = "percentual" | "fator";

export interface ParametroModeloApresentacao {
  grupo: string;
  indicador: string;
  parametro: string;
  valor_atual: number;
  valor_padrao: number;
  tipo: TipoParametroModelo;
  atualizado_em: string;
}
export interface ConfiguracaoParametrosModeloApresentacao {
  parametros: ParametroModeloApresentacao[];
}
export interface ParametroModeloIn {
  grupo: string;
  indicador: string;
  parametro: string;
  valor: number;
}
export interface ParametrosModeloIn {
  parametros: ParametroModeloIn[];
}
export interface ErroGrupoParametrosModelo {
  grupo: string;
  mensagem: string;
}
