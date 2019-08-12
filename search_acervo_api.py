import requests
import xml.etree.ElementTree as ET
import xml
import sys
import unicodedata
import xmltodict
from pathlib import Path
from typing import Union, Tuple
import os


class LexmlAcervo(object):
    """
    Classe para realizar consultas ao acervo do Portal LexML (https://www12.senado.leg.br/dados-abertos/conjuntos?grupo=legislacao&portal=legislativo)
    A API do LexML permite realizar pesquisas por meio de URLs e receber o resultado no formato XML. 
    A API segue o padrão definido pelo Biblioteca do Congresso Nova-americano no projeto Search/Retrieval via URL (SRU).
    Documentação do padrão SRU: http://www.loc.gov/standards/sru/
    """

    def __init__(self, query_string: str):
        """
        A string de consulta a API faz uso do padrão CQL (Contextual Query Language).
        A especificação da query CQL pode ser encontrada em https://www.loc.gov/standards/sru/cql/spec.html
        
        Parâmetros:
            query_string: string de consulta no padrão CQL
        
        Exemplo: "date=2019"
        """
        self.__BASE_URL = "https://www.lexml.gov.br/busca/SRU?operation=searchRetrieve&version=1.1&query="
        self.__START_REC = "&startRecord="
        self.__MAXIMUM_REC = "&maximumRecords="
        # inicializa o container que armazenará o resultado das querys
        self.containerOfXmlFiles = []
        self.__query_string = query_string
        self.__overall_query_objects_tracker = 0
        self.__total_objects_of_query = None
        self.__completed_query = False

    def __addToContainerOfXmlFiles(self, tree: xml.etree.ElementTree.ElementTree):
        """
        Adiciona o resultado de uma paginação da query ao container de dados.
        """
        self.containerOfXmlFiles.append(tree)
        return None

    def query(
        self, startRecord: int, maximumRecordsPerPage: int
    ) -> Tuple[xml.etree.ElementTree.ElementTree, int, int]:
        """
        Realiza uma query a partir da query string definida na inicialização da instância.

        Parâmetros:
            startRecord: posição inicial no set de resultado da query
            maximumRecordsPerPage: número máximo de resultados por paginação.
        """
        if self.__completed_query:
            print(
                f"Todos os objetos para a query {self.__query_string} foram consumidos."
            )
        search_string = self.__query_string.replace(" ", "%20")
        url = "".join(
            [
                self.__BASE_URL,
                search_string,
                self.__START_REC,
                str(startRecord),
                self.__MAXIMUM_REC,
                str(maximumRecordsPerPage),
            ]
        )
        try:
            r = requests.get(url)
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            print(f"Ocorreu um erro na requisição a API: {err}")
            tree = self.loadIntoXml(r)
            if "diagnostics" in tree.getroot().tag:
                diagnosticoErro = self.parseError(tree)
                print(diagnosticoErro)
                return None
        else:
            tree = self.loadIntoXml(r)
            # verifica se foi uma query válida
            if "diagnostics" in tree.getroot().tag:
                diagnosticoErro = self.parseError(tree)
                print(diagnosticoErro)
                return None
            # verifica se a query retornou algum resultado
            numeroObjetos = int(list(tree.getroot())[1].text)
            if not self.__total_objects_of_query:
                self.__total_objects_of_query = numeroObjetos
            if numeroObjetos == 0:
                print(f"A query {search_string} não retornou nenhum resultado.")
            self.__addToContainerOfXmlFiles(tree)
            # calcula o número de objetos ainda há serem consultados
            self.__overall_query_objects_tracker += maximumRecordsPerPage
            remain_objects = numeroObjetos - self.__overall_query_objects_tracker
            if self.__overall_query_objects_tracker >= numeroObjetos:
                print("Todos os objetos foram consultados.")
                print("Finalizado a paginação da query.")
                self.__completed_query = True
            if not self.__completed_query:
                print(
                    f"Retornando objetos de {startRecord} a {self.__overall_query_objects_tracker}."
                )
                print(f"Restam {remain_objects} a serem consultados pela query: {url}")
            start_record_next_query = self.__overall_query_objects_tracker + 1
            return tree, start_record_next_query, maximumRecordsPerPage

    def automatic_pagination(self, startRecord, maximumRecordsPerPage):
        """
        Realiza paginação automática até consumir todos os resultados
        da query string definida na inicialização do instância.

        Parâmetros:
        startRecord: posição inicial no set de resultado da query
        maximumRecordsPerPage: número máximo de resultados por paginação.
        """
        while not self.__completed_query:
            tree, startRecord, maximumRecordsPerPage = self.query(
                startRecord, maximumRecordsPerPage
            )
            self.automatic_pagination(startRecord, maximumRecordsPerPage)

    def parseError(self, tree: xml.etree.ElementTree.ElementTree) -> str:
        """
        Avalia se a query string retorna uma resposta válida.

        Parâmetros:
        tree: objeto do parser de xml
        """
        # verifica se foi uma query válida
        if "diagnostics" in tree.getroot().tag:
            try:
                type_error, message_error = (
                    tree.getiterator()[3].text,
                    tree.getiterator()[4].text,
                )
            except IndexError:
                message_error = tree.getiterator()[3].text
                return f"Messagem de Erro: {message_error}"
            else:
                return f"Messagem de Erro: {type_error}: {message_error}"

    def loadIntoXml(
        self, response: requests.models.Response
    ) -> xml.etree.ElementTree.ElementTree:
        """
        Recebe a resposta do request a API e o carrega no parser de XML

        Parâmetros:
            response: reposta do request GET feito a API.
        """
        contents = unicodedata.normalize("NFKD", response.content.decode("utf-8"))
        root = ET.fromstring(contents)
        tree = ET.ElementTree(root)
        return tree

    def saveResults(self, path: str, filename: str):
        """
        Itera sobre o container de objetos XML coletados da API e os persiste em arquivos
        XML.

        Parâmetros:
            path: Path para salvar os arquivos XML
            filename: nome base dos arquivos a serem salvos.
        """
        path_to_save = Path(path)
        try:
            path_to_save.mkdir(parents=True, exist_ok=True)
        except FileNotFoundError:
            raise FileNotFoundError()
        for index, xmlfile in enumerate(self.containerOfXmlFiles):
            aggName = f"{index}_{filename}.xml"
            full_xml_filename = path_to_save / aggName
            try:
                xmlfile.write(full_xml_filename, encoding="utf-8")
            except FileNotFoundError:
                raise FileNotFoundError()


class XmlToJson:

    __BASE_URL = "https://www.lexml.gov.br/urn/"

    def __init__(self, xmlfile, encoding="utf8"):
        with open(xmlfile, "r", encoding=encoding) as f:
            self.xml = f.read()
            self.container_of_json = []

    def __parseXml(self, _, document):
        data = {
            "tipoDocumento": document["tipoDocumento"],
            "facet-tipoDocumento": document["facet-tipoDocumento"],
            "data": document["dc:date"],
            "urn": document["urn"],
            "url": f"{self.__BASE_URL}{document['urn']}",
            "localidade": document["localidade"],
            "facet-localidade": document["facet-localidade"],
            "autoridade": document["autoridade"],
            "facet-autoridade": document["facet-autoridade"],
            "facet-tipoDocumento": document["facet-tipoDocumento"],
            "title": document["dc:title"],
            "description": document["dc:description"],
            "type": document["dc:type"],
            "identifier": document["dc:identifier"],
        }
        self.container_of_json.append(data)
        return True

    def parseToJson(self):
        xmltodict.parse(self.xml, item_depth=5, item_callback=self.__parseXml)
        return self.container_of_json