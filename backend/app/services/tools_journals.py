"""Journal search sources — verbatim port of the Django helpers in documents/views.py
(fetch_journals_from_springer / _elsevier / _pubmed and the create_or_update_* helpers).

The fetch functions are copied unchanged (same mock data, same matching rules, same
Elsevier catalogue, same PubMed two-step E-utilities calls); only `django.conf.settings`
is replaced by `app.config.settings` and `print` by logging.
"""
import logging

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Journal, User, utcnow

log = logging.getLogger("turadome.tools.journals")


def print(*args, **kwargs):  # noqa: A001 — keep the original diagnostic lines, routed to logging
    log.info(" ".join(str(a) for a in args))


def fetch_journals_from_springer(search_query, limit=100):
    """Fetch journals from Springer Nature API"""
    
    try:
        api_key = settings.SPRINGER_API_KEY
        if api_key == 'YOUR_SPRINGER_API_KEY' or not api_key:
            # Return mock data for demonstration if no API key is configured
            print(f"No Springer API key configured. Using mock data for: {search_query}")
            
            # Mock data that would come from Springer API
            mock_journals = []
            if 'cancer' in search_query.lower() or 'biomarker' in search_query.lower():
                mock_journals = [
                    {
                        'name': 'Journal of Cancer Biology & Therapy',
                        'publisher': 'Springer Nature',
                        'publishing_model': 'hybrid',
                        'issn': '1234-5678',
                        'eissn': '8765-4321',
                        'subject': 'Cancer Research',
                        'url': 'https://link.springer.com/journal/sample1',
                    },
                    {
                        'name': 'Biomarker Research',
                        'publisher': 'Springer Nature',
                        'publishing_model': 'open_access',
                        'issn': '2234-5678',
                        'eissn': '8765-4322',
                        'subject': 'Biomarkers',
                        'url': 'https://link.springer.com/journal/sample2',
                    }
                ]
            elif 'artificial intelligence' in search_query.lower() or 'ai' in search_query.lower():
                mock_journals = [
                    {
                        'name': 'Artificial Intelligence Review',
                        'publisher': 'Springer Nature',
                        'publishing_model': 'hybrid',
                        'issn': '3234-5678',
                        'eissn': '8765-4323',
                        'subject': 'Artificial Intelligence',
                        'url': 'https://link.springer.com/journal/sample3',
                    }
                ]
            
            return mock_journals
        
        url = f"{settings.SPRINGER_API_BASE_URL}?q={search_query}&p={limit}&api_key={api_key}"
        print(f"Calling Springer API: {url}")
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract unique journals from the response
        journals_found = set()
        journal_details = []
        
        for record in data.get('records', []):
            journal_name = record.get('publicationName')
            if journal_name and journal_name not in journals_found:
                journals_found.add(journal_name)
                
                # Extract additional information if available
                journal_info = {
                    'name': journal_name,
                    'publisher': record.get('publisher', 'Springer Nature'),
                    'publishing_model': 'hybrid',  # Default for Springer journals
                    'issn': record.get('issn', ''),
                    'eissn': record.get('eissn', ''),
                    'subject': record.get('subject', ''),
                    'doi': record.get('doi', ''),
                    'publication_date': record.get('publicationDate', ''),
                    'content_type': record.get('contentType', ''),
                    'url': record.get('url', ''),
                }
                journal_details.append(journal_info)
        
        print(f"Springer API returned {len(journal_details)} journals")
        return journal_details
        
    except requests.RequestException as e:
        print(f"Springer API request failed: {e}")
        return []
    except Exception as e:
        print(f"Error processing Springer API response: {e}")
        return []



def fetch_journals_from_elsevier(search_query, limit=50):
    """Fetch oncology journals from Elsevier with comprehensive real data"""
    import urllib.parse
    
    try:
        # Get all real Elsevier oncology journals based on query
        oncology_keywords = ['cancer', 'oncology', 'tumor', 'biomarker', 'chemotherapy', 'radiotherapy', 'immunotherapy']
        
        # Check if search query matches oncology terms
        is_oncology_search = any(keyword.lower() in search_query.lower() for keyword in oncology_keywords)
        
        # Comprehensive list of REAL Elsevier oncology journals from https://journalfinder.elsevier.com/
        elsevier_oncology_journals = [
            {
                'name': 'Cancer Letters',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0304-3835',
                'eissn': '1872-7980',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-letters',
                'impact_factor': 8.679,
                'scope': 'Cancer research, molecular biology, cell biology'
            },
            {
                'name': 'European Journal of Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription', 
                'issn': '0959-8049',
                'eissn': '1879-0852',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/european-journal-of-cancer',
                'impact_factor': 9.162,
                'scope': 'Clinical and translational cancer research'
            },
            {
                'name': 'Lung Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0169-5002',
                'eissn': '1872-8332',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/lung-cancer',
                'impact_factor': 5.604,
                'scope': 'Lung cancer research and treatment'
            },
            {
                'name': 'Gynecologic Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0090-8258',
                'eissn': '1095-6859',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/gynecologic-oncology',
                'impact_factor': 5.304,
                'scope': 'Gynecologic cancer research'
            },
            {
                'name': 'Oral Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1368-8375',
                'eissn': '1879-0593',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/oral-oncology',
                'impact_factor': 4.972,
                'scope': 'Head and neck cancer research'
            },
            {
                'name': 'Cancer Treatment Reviews',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0305-7372',
                'eissn': '1532-1967',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-treatment-reviews',
                'impact_factor': 9.751,
                'scope': 'Cancer treatment and therapy reviews'
            },
            {
                'name': 'Radiotherapy and Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0167-8140',
                'eissn': '1879-0887',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/radiotherapy-and-oncology',
                'impact_factor': 6.126,
                'scope': 'Radiation oncology and therapy'
            },
            {
                'name': 'Journal of Surgical Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0022-4790',
                'eissn': '1096-9098',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/journal-of-surgical-oncology',
                'impact_factor': 3.398,
                'scope': 'Surgical oncology and cancer surgery'
            },
            {
                'name': 'Cancer Cell',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1535-6108',
                'eissn': '1878-3686',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-cell',
                'impact_factor': 50.3,
                'scope': 'Cancer biology and mechanisms'
            },
            {
                'name': 'Clinical Cancer Research',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1078-0432',
                'eissn': '1557-3265',
                'subject': 'Oncology',
                'url': 'https://clincancerres.aacrjournals.org/',
                'impact_factor': 13.801,
                'scope': 'Clinical cancer research and treatment'
            },
            {
                'name': 'Molecular Cancer Therapeutics',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1535-7163',
                'eissn': '1538-8514',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/molecular-cancer-therapeutics',
                'impact_factor': 5.792,
                'scope': 'Cancer drug development and therapeutics'
            },
            {
                'name': 'Cancer Biomarkers',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1574-0153',
                'eissn': '1875-8592',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-biomarkers',
                'impact_factor': 3.436,
                'scope': 'Cancer biomarkers and diagnostics'
            },
            {
                'name': 'Journal of Cancer Research and Clinical Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0171-5216',
                'eissn': '1432-1335',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/journal-of-cancer-research-and-clinical-oncology',
                'impact_factor': 4.024,
                'scope': 'Clinical and experimental cancer research'
            },
            {
                'name': 'Cancer Medicine',
                'publisher': 'Elsevier',
                'publishing_model': 'open_access',
                'issn': '2045-7634',
                'eissn': '2045-7634',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-medicine',
                'impact_factor': 4.711,
                'scope': 'Translational cancer research'
            },
            {
                'name': 'International Journal of Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0020-7136',
                'eissn': '1097-0215',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/international-journal-of-cancer',
                'impact_factor': 7.316,
                'scope': 'Cancer research and epidemiology'
            },
            {
                'name': 'Critical Reviews in Oncology/Hematology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1040-8428',
                'eissn': '1879-0461',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/critical-reviews-in-oncology-hematology',
                'impact_factor': 6.625,
                'scope': 'Oncology and hematology reviews'
            },
            {
                'name': 'Cancer Epidemiology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1877-7821',
                'eissn': '1877-783X',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-epidemiology',
                'impact_factor': 2.974,
                'scope': 'Cancer epidemiology and prevention'
            },
            {
                'name': 'Seminars in Cancer Biology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1044-579X',
                'eissn': '1096-3650',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/seminars-in-cancer-biology',
                'impact_factor': 15.707,
                'scope': 'Cancer biology and mechanisms'
            },
            {
                'name': 'Translational Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'open_access',
                'issn': '1936-5233',
                'eissn': '1936-5233',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/translational-oncology',
                'impact_factor': 4.803,
                'scope': 'Translational cancer research'
            },
            {
                'name': 'European Journal of Surgical Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0748-7983',
                'eissn': '1532-2157',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/european-journal-of-surgical-oncology',
                'impact_factor': 4.321,
                'scope': 'Surgical oncology in Europe'
            },
            {
                'name': 'Clinical Breast Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1526-8209',
                'eissn': '1938-0666',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/clinical-breast-cancer',
                'impact_factor': 3.078,
                'scope': 'Breast cancer clinical research'
            },
            {
                'name': 'Clinical Colorectal Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1533-0028',
                'eissn': '1938-0674',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/clinical-colorectal-cancer',
                'impact_factor': 3.218,
                'scope': 'Colorectal cancer research'
            },
            {
                'name': 'Clinical Genitourinary Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1558-7673',
                'eissn': '1938-0682',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/clinical-genitourinary-cancer',
                'impact_factor': 2.944,
                'scope': 'Genitourinary cancer research'
            },
            {
                'name': 'Clinical Lung Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1525-7304',
                'eissn': '1938-0690',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/clinical-lung-cancer',
                'impact_factor': 5.515,
                'scope': 'Lung cancer clinical research'
            },
            {
                'name': 'Clinical Lymphoma Myeloma and Leukemia',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '2152-2650',
                'eissn': '2152-2669',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/clinical-lymphoma-myeloma-and-leukemia',
                'impact_factor': 2.925,
                'scope': 'Hematologic malignancies'
            },
            {
                'name': 'Cancer Genetics',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '2210-7762',
                'eissn': '2210-7770',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-genetics',
                'impact_factor': 4.514,
                'scope': 'Cancer genetics and genomics'
            },
            {
                'name': 'Molecular Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'open_access',
                'issn': '1574-7891',
                'eissn': '1878-0261',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/molecular-oncology',
                'impact_factor': 6.574,
                'scope': 'Molecular aspects of cancer'
            },
            {
                'name': 'Urologic Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1078-1439',
                'eissn': '1873-2496',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/urologic-oncology-seminars-and-original-investigations',
                'impact_factor': 2.882,
                'scope': 'Urologic cancer research'
            },
            {
                'name': 'Journal of Thoracic Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1556-0864',
                'eissn': '1556-1380',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/journal-of-thoracic-oncology',
                'impact_factor': 20.121,
                'scope': 'Thoracic cancer research'
            },
            {
                'name': 'Cancer Immunology Research',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '2326-6066',
                'eissn': '2326-6074',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-immunology-research',
                'impact_factor': 10.202,
                'scope': 'Cancer immunology and immunotherapy'
            },
            {
                'name': 'Neuro-Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1522-8517',
                'eissn': '1523-5866',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/neuro-oncology',
                'impact_factor': 10.247,
                'scope': 'Brain and nervous system tumors'
            },
            {
                'name': 'Pediatric Blood & Cancer',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1545-5009',
                'eissn': '1545-5017',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/pediatric-blood-and-cancer',
                'impact_factor': 3.315,
                'scope': 'Pediatric hematology and oncology'
            },
            {
                'name': 'Clinical Cancer Drugs',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '2212-6975',
                'eissn': '2212-6983',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/clinical-cancer-drugs',
                'impact_factor': 3.892,
                'scope': 'Cancer drug therapy and development'
            },
            {
                'name': 'Oncology Research',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0965-0407',
                'eissn': '1555-3906',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/oncology-research',
                'impact_factor': 4.892,
                'scope': 'Experimental oncology research'
            },
            {
                'name': 'Cancer Chemotherapy and Pharmacology',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0344-5704',
                'eissn': '1432-0843',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-chemotherapy-and-pharmacology',
                'impact_factor': 4.13,
                'scope': 'Cancer chemotherapy and drug development'
            },
            {
                'name': 'Oncology Reports',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1021-335X',
                'eissn': '1791-2431',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/oncology-reports',
                'impact_factor': 5.502,
                'scope': 'Experimental and clinical oncology'
            },
            {
                'name': 'International Journal of Radiation Oncology Biology Physics',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '0360-3016',
                'eissn': '1879-355X',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/international-journal-of-radiation-oncology-biology-physics',
                'impact_factor': 7.038,
                'scope': 'Radiation oncology and medical physics'
            },
            {
                'name': 'Cancer Prevention Research',
                'publisher': 'Elsevier',
                'publishing_model': 'subscription',
                'issn': '1940-6207',
                'eissn': '1940-6215',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/cancer-prevention-research',
                'impact_factor': 4.439,
                'scope': 'Cancer prevention and early detection'
            },
            {
                'name': 'Journal of Cancer Therapy',
                'publisher': 'Elsevier',
                'publishing_model': 'open_access',
                'issn': '2151-1934',
                'eissn': '2151-1942',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/journal-of-cancer-therapy',
                'impact_factor': 2.156,
                'scope': 'Cancer treatment and therapy'
            },
            {
                'name': 'Experimental Hematology & Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'open_access',
                'issn': '2162-3619',
                'eissn': '2162-3619',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/experimental-hematology-and-oncology',
                'impact_factor': 9.414,
                'scope': 'Experimental hematology and oncology'
            },
            {
                'name': 'Precision Oncology',
                'publisher': 'Elsevier',
                'publishing_model': 'open_access',
                'issn': '2590-1613',
                'eissn': '2590-1613',
                'subject': 'Oncology',
                'url': 'https://www.sciencedirect.com/journal/precision-oncology',
                'impact_factor': 6.824,
                'scope': 'Precision medicine in oncology'
            }
        ]
        
        # Filter journals based on search query
        filtered_journals = []
        search_lower = search_query.lower()
        
        for journal in elsevier_oncology_journals:
            # Check if search query matches journal name, subject, or scope
            # More precise matching - look for the search term IN the journal data, not keywords in search
            if (search_lower in journal['name'].lower() or 
                search_lower in journal['subject'].lower() or 
                search_lower in journal['scope'].lower()):
                filtered_journals.append(journal)
        
        # If no specific matches found but query is oncology-related, return relevant subset
        if not filtered_journals and any(keyword in search_lower for keyword in ['cancer', 'oncology', 'tumor', 'biomarker']):
            # Return a diverse subset of oncology journals
            filtered_journals = elsevier_oncology_journals[:limit]
        
        # Return up to limit journals
        print(f"Elsevier: Found {len(filtered_journals)} matching journals for '{search_query}'")
        return filtered_journals[:limit]
        
    except Exception as e:
        print(f"Error in Elsevier journal search: {e}")
        return []



def fetch_journals_from_pubmed(search_query, limit=50):
    """Fetch journals from PubMed API based on search query"""
    from xml.etree import ElementTree as ET
    import urllib.parse
    
    try:
        api_key = settings.PUBMED_API_KEY
        
        # Step 1: Search for article IDs using the keyword
        esearch_url = settings.PUBMED_ESEARCH_URL
        search_params = {
            "db": "pubmed",
            "term": search_query,
            "retmax": min(limit * 2, 200),  # Get more articles to find diverse journals
            "retmode": "xml"
        }
        
        if api_key:
            search_params["api_key"] = api_key
            
        print(f"Calling PubMed Search API: {esearch_url}")
        
        search_response = requests.get(esearch_url, params=search_params, timeout=10)
        search_response.raise_for_status()
        
        search_xml = ET.fromstring(search_response.content)
        id_list = [id_elem.text for id_elem in search_xml.findall(".//Id")]
        
        if not id_list:
            print("No PubMed articles found for query")
            return []
            
        print(f"Found {len(id_list)} PubMed articles")
        
        # Step 2: Fetch article metadata
        efetch_url = settings.PUBMED_EFETCH_URL
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list[:100]),  # Limit to avoid too large requests
            "retmode": "xml"
        }
        
        if api_key:
            fetch_params["api_key"] = api_key
            
        fetch_response = requests.get(efetch_url, params=fetch_params, timeout=15)
        fetch_response.raise_for_status()
        
        articles_xml = ET.fromstring(fetch_response.content)
        
        # Step 3: Extract journal information
        journal_set = set()
        journals_info = []
        
        for article in articles_xml.findall(".//PubmedArticle"):
            journal_elem = article.find(".//Journal")
            if journal_elem is not None:
                title_elem = journal_elem.find("Title")
                if title_elem is not None:
                    journal_title = title_elem.text.strip()
                    
                    if journal_title not in journal_set:
                        journal_set.add(journal_title)
                        
                        # Extract additional information
                        issn_elem = journal_elem.find("ISSN")
                        issn = issn_elem.text.strip() if issn_elem is not None else ""
                        
                        # Extract publication info
                        pub_info = article.find(".//PublicationTypeList")
                        pub_types = []
                        if pub_info is not None:
                            for pub_type in pub_info.findall("PublicationType"):
                                if pub_type.text:
                                    pub_types.append(pub_type.text.strip())
                        
                        # Create journal info
                        journal_info = {
                            'name': journal_title,
                            'publisher': 'Various Publishers',  # PubMed doesn't provide publisher info
                            'publishing_model': 'subscription',  # Default assumption
                            'issn': issn,
                            'eissn': '',  # Not available in basic PubMed data
                            'subject': ', '.join(pub_types) if pub_types else 'Medical Research',
                            'url': f'https://pubmed.ncbi.nlm.nih.gov/?term={urllib.parse.quote(journal_title)}',
                            'source': 'pubmed_api'
                        }
                        journals_info.append(journal_info)
                        
                        # Limit results
                        if len(journals_info) >= limit:
                            break
        
        print(f"PubMed: Found {len(journals_info)} unique journals for '{search_query}'")
        return journals_info
        
    except requests.RequestException as e:
        print(f"PubMed API request failed: {e}")
        return []
    except ET.ParseError as e:
        print(f"Error parsing PubMed XML response: {e}")
        return []
    except Exception as e:
        print(f"Error in PubMed journal search: {e}")
        return []



# ---------------------------------------------------------------------------
# get_or_create helpers (Journal.objects.get_or_create(name=...) semantics)
# ---------------------------------------------------------------------------
PUBLISHING_MODEL_DISPLAY = {"open_access": "Open Access", "subscription": "Subscription", "hybrid": "Hybrid"}


def _new_journal(name: str, user: User, **fields) -> Journal:
    """A Journal row with every Django model default filled in."""
    values = dict(
        name=name, publisher=None, issn=None, eissn=None, publishing_model="hybrid",
        journal_impact_factor=None, impact_factor_year=None, downloads=0, submission_to_decision_days=None,
        primary_subject="", secondary_subjects="", website_url=None, submission_url=None,
        scope_and_aims="", cover_image=None, keywords="", is_active=1, created_by_id=user.id,
    )
    values.update(fields)
    return Journal(**values)


def _get_or_create(db: Session, name: str, user: User, defaults: dict) -> tuple[Journal, bool]:
    rows = db.execute(select(Journal).where(Journal.name == name).limit(2)).scalars().all()
    if len(rows) > 1:
        raise RuntimeError("get() returned more than one Journal -- it returned 2!")
    if rows:
        return rows[0], False
    journal = _new_journal(name, user, **defaults)
    db.add(journal)
    db.flush()
    return journal, True


def _guarded(db: Session, label: str, fn):
    """Run one create/update in a savepoint; on any error log it and return None (Django's try/except)."""
    try:
        with db.begin_nested():
            return fn()
    except Exception as e:  # noqa: BLE001
        print(f"Error creating/updating journal{label}: {e}")
        return None


def create_or_update_journal_from_springer(db: Session, journal_info, user):
    def run():
        journal, created = _get_or_create(db, journal_info['name'], user, {
            'publisher': journal_info.get('publisher', 'Springer Nature'),
            'publishing_model': journal_info.get('publishing_model', 'hybrid'),
            'issn': journal_info.get('issn', ''),
            'eissn': journal_info.get('eissn', ''),
            'primary_subject': journal_info.get('subject', ''),
            'keywords': journal_info.get('subject', ''),
            'website_url': journal_info.get('url', ''),
        })
        if not created:
            journal.publisher = journal_info.get('publisher', journal.publisher)
            journal.issn = journal_info.get('issn', journal.issn) or journal.issn
            journal.eissn = journal_info.get('eissn', journal.eissn) or journal.eissn
            journal.website_url = journal_info.get('url', journal.website_url) or journal.website_url
            journal.updated_at = utcnow()  # save() bumps auto_now
            db.flush()
        return journal
    return _guarded(db, "", run)


def create_or_update_journal_from_elsevier(db: Session, journal_info, user):
    def run():
        journal, created = _get_or_create(db, journal_info['name'], user, {
            'primary_subject': journal_info.get('subject', ''),
            'keywords': journal_info.get('subject', ''),
            'website_url': journal_info.get('url', ''),
        })
        if not created:
            if not journal.publisher or journal.publisher == 'Unknown':
                journal.publisher = journal_info.get('publisher', journal.publisher)
            journal.issn = journal_info.get('issn', journal.issn) or journal.issn
            journal.eissn = journal_info.get('eissn', journal.eissn) or journal.eissn
            journal.website_url = journal_info.get('url', journal.website_url) or journal.website_url
            journal.updated_at = utcnow()
            db.flush()
        return journal
    return _guarded(db, " from Elsevier", run)


def create_or_update_journal_from_pubmed(db: Session, journal_info, user):
    def run():
        journal, created = _get_or_create(db, journal_info['name'], user, {
            'primary_subject': journal_info.get('subject', 'Medical Research'),
            'keywords': journal_info.get('subject', ''),
            'website_url': journal_info.get('url', ''),
        })
        if not created:
            if not journal.issn and journal_info.get('issn'):
                journal.issn = journal_info.get('issn', journal.issn)
            if not journal.primary_subject and journal_info.get('subject'):
                journal.primary_subject = journal_info.get('subject', journal.primary_subject)
            if not journal.website_url and journal_info.get('url'):
                journal.website_url = journal_info.get('url', journal.website_url)
            journal.updated_at = utcnow()
            db.flush()
        return journal
    return _guarded(db, " from PubMed", run)


# ---------------------------------------------------------------------------
# journal_search_api
# ---------------------------------------------------------------------------
def secondary_subjects_list(journal: Journal) -> list[str]:
    if journal.secondary_subjects:
        return [s.strip() for s in journal.secondary_subjects.split(',')]
    return []


def journal_dict(journal: Journal, saved_ids: set[int], source: str) -> dict:
    from app.core.files import media_url
    return {
        'id': journal.id,
        'name': journal.name,
        'publisher': journal.publisher or '',
        'publishing_model': PUBLISHING_MODEL_DISPLAY.get(journal.publishing_model, journal.publishing_model),
        'impact_factor': str(journal.journal_impact_factor) if journal.journal_impact_factor else 'N/A',
        'impact_factor_year': journal.impact_factor_year or '',
        'downloads': journal.downloads,
        'submission_days': journal.submission_to_decision_days or 'N/A',
        'primary_subject': journal.primary_subject,
        'secondary_subjects': secondary_subjects_list(journal),
        'is_saved': journal.id in saved_ids,
        'cover_image_url': media_url(journal.cover_image) if journal.cover_image else None,
        'source': source,
        'submission_url': journal.submission_url or '',
        'website_url': journal.website_url or '',
    }


def _local_query(search_query: str):
    from sqlalchemy import or_
    like = f"%{search_query}%"
    return select(Journal).where(
        or_(
            Journal.name.ilike(like), Journal.keywords.ilike(like), Journal.primary_subject.ilike(like),
            Journal.secondary_subjects.ilike(like), Journal.scope_and_aims.ilike(like), Journal.publisher.ilike(like),
        ),
        Journal.is_active == 1,
    ).distinct()


def _saved_ids(db: Session, user: User) -> set[int]:
    from app.models import UserJournalSelection
    return set(db.execute(select(UserJournalSelection.journal_id).where(UserJournalSelection.user_id == user.id)).scalars())


def search_journals(db: Session, user: User, search_query: str) -> dict:
    """Body of journal_search_api for a non-empty query (local DB + Springer + Elsevier + PubMed)."""
    try:
        local_journals = db.execute(
            _local_query(search_query).order_by(Journal.journal_impact_factor.desc(), Journal.name).limit(20)
        ).scalars().all()

        springer_journals = fetch_journals_from_springer(search_query, limit=50)
        elsevier_journals = fetch_journals_from_elsevier(search_query, limit=50)
        pubmed_journals = fetch_journals_from_pubmed(search_query, limit=30)

        springer_api_journals = []
        for springer_journal in springer_journals[:15]:
            journal = create_or_update_journal_from_springer(db, springer_journal, user)
            if journal:
                springer_api_journals.append(journal)

        elsevier_api_journals = []
        for elsevier_journal in elsevier_journals[:40]:
            journal = create_or_update_journal_from_elsevier(db, elsevier_journal, user)
            if journal:
                elsevier_api_journals.append(journal)

        pubmed_api_journals = []
        for pubmed_journal in pubmed_journals[:25]:
            journal = create_or_update_journal_from_pubmed(db, pubmed_journal, user)
            if journal:
                pubmed_api_journals.append(journal)
        db.commit()

        api_journals = springer_api_journals + elsevier_api_journals + pubmed_api_journals

        all_journals = list(local_journals)
        existing_journal_names = {journal.name.lower() for journal in all_journals}
        for api_journal in api_journals:
            if api_journal.name.lower() not in existing_journal_names:
                all_journals.append(api_journal)
                existing_journal_names.add(api_journal.name.lower())

        saved = _saved_ids(db, user)
        springer_ids = {j.id for j in springer_api_journals}
        elsevier_ids = {j.id for j in elsevier_api_journals}
        pubmed_ids = {j.id for j in pubmed_api_journals}
        journal_data = []
        for journal in all_journals:
            source = 'local'
            if journal.id in springer_ids:
                source = 'springer_api'
            elif journal.id in elsevier_ids:
                source = 'elsevier_api'
            elif journal.id in pubmed_ids:
                source = 'pubmed_api'
            journal_data.append(journal_dict(journal, saved, source))

        return {
            'journals': journal_data,
            'count': len(journal_data),
            'query': search_query,
            'sources': {
                'local_count': len(local_journals),
                'springer_api_count': len(springer_api_journals),
                'elsevier_api_count': len(elsevier_api_journals),
                'pubmed_api_count': len(pubmed_api_journals),
                'total_api_count': len(api_journals),
                'total_count': len(all_journals),
            },
        }
    except Exception:  # noqa: BLE001 — fall back to local search only, like Django
        db.rollback()
        local_journals = db.execute(_local_query(search_query).limit(20)).scalars().all()
        saved = _saved_ids(db, user)
        journal_data = [journal_dict(j, saved, 'local') for j in local_journals]
        return {
            'journals': journal_data,
            'count': len(journal_data),
            'query': search_query,
            'warning': 'API search failed, showing local results only',
            'sources': {'local_count': len(local_journals), 'api_count': 0, 'total_count': len(local_journals)},
        }
