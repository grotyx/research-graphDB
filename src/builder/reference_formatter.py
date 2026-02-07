"""Reference Style Formatter for Medical Papers.

다양한 저널 인용 스타일을 지원하는 참고문헌 포맷터.
저널별 커스텀 스타일 저장 및 관리 기능 포함.

Usage:
    formatter = ReferenceFormatter()

    # 기본 스타일로 포맷
    ref = formatter.format(paper_metadata, style="vancouver")

    # 저널 스타일로 포맷
    ref = formatter.format(paper_metadata, journal="Spine")

    # 새 저널 스타일 추가
    formatter.add_journal_style("Spine J", {
        "base_style": "vancouver",
        "author_format": "last_initials",
        "et_al_threshold": 6,
        ...
    })
"""

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Literal
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# 기본 스타일 타입
StyleType = Literal[
    "vancouver", "ama", "apa", "jbjs", "spine",
    "nlm", "harvard", "chicago", "bibtex", "ris", "endnote"
]


@dataclass
class AuthorFormatConfig:
    """저자 이름 포맷 설정."""
    format: str = "last_initials"  # last_initials, last_first, full
    separator: str = ", "
    last_separator: str = ", "  # 마지막 저자 앞 구분자
    et_al_threshold: int = 6  # 이 수 이상이면 et al.
    et_al_min: int = 3  # et al. 사용 시 표시할 최소 저자 수
    et_al_text: str = "et al"
    initials_format: str = "no_space"  # no_space (SM), space (S M), dots (S.M.)
    hyphen_handling: str = "keep"  # keep (S-M), remove (SM)


@dataclass
class JournalFormatConfig:
    """저널명 포맷 설정."""
    use_abbreviation: bool = True
    italicize: bool = False
    bold: bool = False


@dataclass
class DateFormatConfig:
    """날짜 포맷 설정."""
    format: str = "year_only"  # year_only, year_month, full
    position: str = "after_authors"  # after_authors, after_title, end


@dataclass
class StyleConfig:
    """인용 스타일 전체 설정."""
    name: str = ""
    base_style: Optional[str] = None  # 상속받을 기본 스타일

    # 저자 설정
    author: AuthorFormatConfig = field(default_factory=AuthorFormatConfig)

    # 제목 설정
    title_quotes: bool = False
    title_italics: bool = False
    title_period: bool = True
    title_case: str = "sentence"  # sentence, title, original

    # 저널 설정
    journal: JournalFormatConfig = field(default_factory=JournalFormatConfig)

    # 날짜 설정
    date: DateFormatConfig = field(default_factory=DateFormatConfig)

    # 볼륨/이슈/페이지 설정
    volume_bold: bool = False
    volume_format: str = "{volume}"  # "{volume}", "{volume}({issue})"
    issue_in_parens: bool = True
    pages_format: str = "full"  # full (123-130), abbreviated (123-30)
    pages_prefix: str = ":"

    # DOI/PMID 설정
    include_doi: bool = False
    doi_format: str = "doi:{doi}"
    include_pmid: bool = False
    pmid_format: str = "PMID: {pmid}"

    # 구분자
    element_separator: str = ". "
    final_period: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환."""
        return {
            "name": self.name,
            "base_style": self.base_style,
            "author": asdict(self.author),
            "title_quotes": self.title_quotes,
            "title_italics": self.title_italics,
            "title_period": self.title_period,
            "title_case": self.title_case,
            "journal": asdict(self.journal),
            "date": asdict(self.date),
            "volume_bold": self.volume_bold,
            "volume_format": self.volume_format,
            "issue_in_parens": self.issue_in_parens,
            "pages_format": self.pages_format,
            "pages_prefix": self.pages_prefix,
            "include_doi": self.include_doi,
            "doi_format": self.doi_format,
            "include_pmid": self.include_pmid,
            "pmid_format": self.pmid_format,
            "element_separator": self.element_separator,
            "final_period": self.final_period,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StyleConfig":
        """딕셔너리에서 생성."""
        config = cls()
        config.name = data.get("name", "")
        config.base_style = data.get("base_style")

        if "author" in data:
            config.author = AuthorFormatConfig(**data["author"])
        if "journal" in data:
            config.journal = JournalFormatConfig(**data["journal"])
        if "date" in data:
            config.date = DateFormatConfig(**data["date"])

        for key in ["title_quotes", "title_italics", "title_period", "title_case",
                    "volume_bold", "volume_format", "issue_in_parens",
                    "pages_format", "pages_prefix", "include_doi", "doi_format",
                    "include_pmid", "pmid_format", "element_separator", "final_period"]:
            if key in data:
                setattr(config, key, data[key])

        return config


# 기본 스타일 정의
DEFAULT_STYLES: Dict[str, StyleConfig] = {
    "vancouver": StyleConfig(
        name="Vancouver (ICMJE)",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            et_al_threshold=6,
            et_al_min=6,
            et_al_text="et al",
            initials_format="no_space",
        ),
        title_period=True,
        title_case="sentence",
        journal=JournalFormatConfig(use_abbreviation=True),
        date=DateFormatConfig(format="year_only", position="after_authors"),
        volume_format="{volume}({issue})",
        pages_prefix=":",
        include_doi=False,
    ),

    "ama": StyleConfig(
        name="AMA (American Medical Association)",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            et_al_threshold=6,
            et_al_min=3,
            et_al_text="et al",
            initials_format="no_space",
        ),
        title_period=True,
        title_case="sentence",
        journal=JournalFormatConfig(use_abbreviation=True, italicize=True),
        date=DateFormatConfig(format="year_only"),
        volume_bold=False,
        volume_format="{volume}({issue})",
        pages_prefix=":",
        include_doi=True,
        doi_format="doi:{doi}",
    ),

    "apa": StyleConfig(
        name="APA 7th Edition",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            last_separator=" & ",
            et_al_threshold=21,
            et_al_min=19,
            et_al_text="... ",
            initials_format="dots",
        ),
        title_period=True,
        title_case="sentence",
        title_italics=False,
        journal=JournalFormatConfig(use_abbreviation=False, italicize=True),
        date=DateFormatConfig(format="year_only", position="after_authors"),
        volume_bold=False,
        volume_format="{volume}({issue})",
        pages_format="full",
        pages_prefix=", ",
        include_doi=True,
        doi_format="https://doi.org/{doi}",
    ),

    "jbjs": StyleConfig(
        name="JBJS (Bone & Joint Journal)",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            et_al_threshold=6,
            et_al_min=6,
            et_al_text="et al",
            initials_format="no_space",
            hyphen_handling="keep",
        ),
        title_period=True,
        title_case="sentence",
        journal=JournalFormatConfig(use_abbreviation=True),
        date=DateFormatConfig(format="year_only"),
        volume_format="{volume}-B({issue})",  # JBJS 특수 포맷
        pages_prefix=":",
        pages_format="abbreviated",
        include_doi=False,
    ),

    "spine": StyleConfig(
        name="Spine Journal",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            et_al_threshold=6,
            et_al_min=3,
            et_al_text="et al",
            initials_format="no_space",
        ),
        title_period=True,
        title_case="sentence",
        journal=JournalFormatConfig(use_abbreviation=True),
        date=DateFormatConfig(format="year_only"),
        volume_format="{volume}({issue})",
        pages_prefix=":",
        include_doi=False,
    ),

    "nlm": StyleConfig(
        name="NLM (National Library of Medicine)",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            et_al_threshold=6,
            et_al_min=6,
            et_al_text="et al",
            initials_format="no_space",
        ),
        title_period=True,
        journal=JournalFormatConfig(use_abbreviation=True),
        date=DateFormatConfig(format="year_month"),
        volume_format="{volume}({issue})",
        include_pmid=True,
    ),

    "harvard": StyleConfig(
        name="Harvard",
        author=AuthorFormatConfig(
            format="last_initials",
            separator=", ",
            last_separator=" and ",
            et_al_threshold=3,
            et_al_min=1,
            et_al_text="et al.",
            initials_format="dots",
        ),
        title_quotes=True,
        journal=JournalFormatConfig(use_abbreviation=False, italicize=True),
        date=DateFormatConfig(format="year_only", position="after_authors"),
        volume_bold=True,
        pages_prefix=", pp. ",
    ),
}


# 기본 저널-스타일 매핑
# 저널명 (대소문자 무관) -> 스타일명
DEFAULT_JOURNAL_MAPPINGS: Dict[str, str] = {
    # Spine Surgery Journals
    "The Spine Journal": "spine",
    "Spine Journal": "spine",
    "Spine": "vancouver",
    "European Spine Journal": "vancouver",
    "Eur Spine J": "vancouver",
    "Global Spine Journal": "vancouver",
    "Glob Spine J": "vancouver",
    "Asian Spine Journal": "vancouver",
    "Asian Spine J": "vancouver",

    # Orthopedic Journals
    "Clinics in Orthopedic Surgery": "vancouver",
    "Clin Orthop Surg": "vancouver",
    "Journal of Bone and Joint Surgery": "jbjs",
    "JBJS": "jbjs",
    "J Bone Joint Surg Am": "jbjs",
    "J Bone Joint Surg Br": "jbjs",

    # General Medical Journals
    "JAMA": "ama",
    "JAMA Surgery": "ama",
    "JAMA Network Open": "ama",
    "New England Journal of Medicine": "vancouver",
    "NEJM": "vancouver",
    "The Lancet": "vancouver",
    "Lancet": "vancouver",
    "BMJ": "vancouver",

    # Neurosurgery Journals
    "Journal of Neurosurgery": "vancouver",
    "J Neurosurg": "vancouver",
    "Journal of Neurosurgery Spine": "vancouver",
    "J Neurosurg Spine": "vancouver",
    "Neurosurgery": "vancouver",
}


@dataclass
class PaperReference:
    """논문 참고문헌 데이터."""
    paper_id: str = ""
    title: str = ""
    authors: List[str] = field(default_factory=list)
    year: int = 0
    month: Optional[int] = None
    journal: str = ""
    journal_abbrev: str = ""
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    pmid: Optional[str] = None

    @classmethod
    def from_metadata(cls, metadata: Dict[str, Any], paper_id: str = "") -> "PaperReference":
        """메타데이터 딕셔너리에서 생성.

        Args:
            metadata: 논문 메타데이터 딕셔너리
            paper_id: 논문 ID (기본값: 메타데이터에서 추출)

        Returns:
            PaperReference 인스턴스
        """
        # year 타입 변환
        year = metadata.get("year", 0)
        if isinstance(year, str):
            try:
                year = int(year)
            except ValueError:
                year = 0

        # authors 검증 및 정제
        authors = metadata.get("authors", [])
        if not isinstance(authors, list):
            authors = []
        # 빈 문자열과 None 제거, 문자열로 변환
        authors = [str(a).strip() for a in authors if a and str(a).strip()]

        return cls(
            paper_id=paper_id or metadata.get("paper_id", ""),
            title=metadata.get("title", "") or "",
            authors=authors,
            year=year,
            month=metadata.get("month"),
            journal=metadata.get("journal", "") or "",
            journal_abbrev=metadata.get("journal_abbrev", "") or "",
            volume=metadata.get("volume"),
            issue=metadata.get("issue"),
            pages=metadata.get("pages"),
            doi=metadata.get("doi"),
            pmid=metadata.get("pmid"),
        )


class ReferenceFormatter:
    """참고문헌 포맷터."""

    def __init__(self, styles_file: Optional[Path] = None):
        """초기화.

        Args:
            styles_file: 저널 스타일 저장 파일 경로
        """
        self.styles: Dict[str, StyleConfig] = DEFAULT_STYLES.copy()
        self.journal_styles: Dict[str, str] = {}  # 저널명 -> 스타일명 매핑
        self.custom_styles: Dict[str, StyleConfig] = {}  # 커스텀 스타일

        # 스타일 파일 경로
        if styles_file:
            self.styles_file = styles_file
        else:
            self.styles_file = Path(__file__).parent.parent.parent / "data" / "styles" / "journal_styles.json"

        # 저장된 스타일 로드
        self._load_styles()

    def _load_styles(self) -> None:
        """저장된 스타일 로드."""
        if not self.styles_file.exists():
            return

        try:
            with open(self.styles_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 저널-스타일 매핑 로드
            self.journal_styles = data.get("journal_mappings", {})

            # 커스텀 스타일 로드
            for name, style_data in data.get("custom_styles", {}).items():
                self.custom_styles[name] = StyleConfig.from_dict(style_data)

            logger.info(f"Loaded {len(self.journal_styles)} journal mappings, "
                       f"{len(self.custom_styles)} custom styles")

        except Exception as e:
            logger.warning(f"Failed to load styles: {e}")

    def _save_styles(self) -> None:
        """스타일 저장."""
        self.styles_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "journal_mappings": self.journal_styles,
            "custom_styles": {
                name: config.to_dict()
                for name, config in self.custom_styles.items()
            },
            "updated_at": datetime.now().isoformat(),
        }

        with open(self.styles_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved styles to {self.styles_file}")

    def get_style(self, style_name: str) -> StyleConfig:
        """스타일 설정 가져오기."""
        # 커스텀 스타일 먼저 확인
        if style_name in self.custom_styles:
            return self.custom_styles[style_name]

        # 기본 스타일 확인
        if style_name in self.styles:
            return self.styles[style_name]

        # 찾지 못하면 vancouver 반환
        logger.warning(f"Style '{style_name}' not found, using vancouver")
        return self.styles["vancouver"]

    def get_journal_style(self, journal_name: str) -> Optional[str]:
        """저널에 매핑된 스타일 가져오기.

        우선순위:
        1. 사용자 저장 매핑 (정확한 이름)
        2. 사용자 저장 매핑 (대소문자 무시)
        3. 기본 매핑 (정확한 이름)
        4. 기본 매핑 (대소문자 무시)
        """
        # 1. 사용자 저장 매핑 - 정확히 일치
        if journal_name in self.journal_styles:
            return self.journal_styles[journal_name]

        # 2. 사용자 저장 매핑 - 대소문자 무시
        journal_lower = journal_name.lower()
        for j, style in self.journal_styles.items():
            if j.lower() == journal_lower:
                return style

        # 3. 기본 매핑 - 정확히 일치
        if journal_name in DEFAULT_JOURNAL_MAPPINGS:
            return DEFAULT_JOURNAL_MAPPINGS[journal_name]

        # 4. 기본 매핑 - 대소문자 무시
        for j, style in DEFAULT_JOURNAL_MAPPINGS.items():
            if j.lower() == journal_lower:
                return style

        return None

    def set_journal_style(self, journal_name: str, style_name: str) -> None:
        """저널에 스타일 매핑 설정."""
        self.journal_styles[journal_name] = style_name
        self._save_styles()
        logger.info(f"Set style '{style_name}' for journal '{journal_name}'")

    def add_custom_style(self, name: str, config: StyleConfig) -> None:
        """커스텀 스타일 추가."""
        config.name = name
        self.custom_styles[name] = config
        self._save_styles()
        logger.info(f"Added custom style '{name}'")

    def list_styles(self) -> Dict[str, Any]:
        """사용 가능한 스타일 목록."""
        # 기본 매핑 + 사용자 매핑 결합 (사용자 매핑이 우선)
        all_journal_mappings = {**DEFAULT_JOURNAL_MAPPINGS, **self.journal_styles}

        return {
            "default_styles": list(self.styles.keys()),
            "custom_styles": list(self.custom_styles.keys()),
            "journal_mappings": list(all_journal_mappings.keys()),
            "journal_mappings_detail": all_journal_mappings,
            "default_journal_count": len(DEFAULT_JOURNAL_MAPPINGS),
            "user_journal_count": len(self.journal_styles),
        }

    def format(
        self,
        paper: PaperReference,
        style: Optional[str] = None,
        journal: Optional[str] = None,
    ) -> str:
        """참고문헌 포맷팅.

        Args:
            paper: 논문 정보
            style: 스타일명 (직접 지정)
            journal: 저널명 (저널에 매핑된 스타일 사용)

        Returns:
            포맷된 참고문헌 문자열
        """
        # 스타일 결정
        if style:
            config = self.get_style(style)
        elif journal:
            mapped_style = self.get_journal_style(journal)
            config = self.get_style(mapped_style or "vancouver")
        else:
            config = self.get_style("vancouver")

        # 포맷팅
        return self._format_with_config(paper, config)

    def _format_with_config(self, paper: PaperReference, config: StyleConfig) -> str:
        """설정에 따라 포맷팅."""
        parts = []

        # 1. 저자
        authors_str = self._format_authors(paper.authors, config.author)
        if authors_str:
            parts.append(authors_str)

        # 2. 제목
        title_str = self._format_title(paper.title, config)
        if title_str:
            parts.append(title_str)

        # 3. 저널명
        journal_name = paper.journal_abbrev if config.journal.use_abbreviation and paper.journal_abbrev else paper.journal
        # 빈 문자열 및 None 처리
        journal_name = journal_name.strip() if journal_name else ""
        has_journal = bool(journal_name)

        if journal_name:
            if config.journal.italicize:
                journal_name = f"*{journal_name}*"
            parts.append(journal_name)

        # 4. 연도, 볼륨, 이슈, 페이지
        pub_info = self._format_publication_info(paper, config)
        if pub_info:
            # 저널명이 있으면 공백으로 연결, 없으면 별도 파트로 추가
            if has_journal and parts:
                parts[-1] = parts[-1] + " " + pub_info
            else:
                parts.append(pub_info)

        # 5. DOI
        if config.include_doi and paper.doi:
            doi_str = config.doi_format.format(doi=paper.doi)
            parts.append(doi_str)

        # 6. PMID
        if config.include_pmid and paper.pmid:
            pmid_str = config.pmid_format.format(pmid=paper.pmid)
            parts.append(pmid_str)

        # 조합
        result = config.element_separator.join(parts)

        # 마지막 마침표
        if config.final_period and result and not result.endswith("."):
            result += "."

        return result

    def _format_authors(self, authors: List[str], config: AuthorFormatConfig) -> str:
        """저자 포맷팅."""
        if not authors:
            return ""

        # et al. 처리
        use_et_al = len(authors) >= config.et_al_threshold
        if use_et_al:
            authors = authors[:config.et_al_min]

        formatted = []
        for author in authors:
            formatted.append(self._format_single_author(author, config))

        # 조합
        if len(formatted) == 1:
            result = formatted[0]
        elif len(formatted) == 2:
            result = f"{formatted[0]}{config.last_separator}{formatted[1]}"
        else:
            result = config.separator.join(formatted[:-1])
            result += f"{config.last_separator}{formatted[-1]}"

        # et al. 추가
        if use_et_al:
            result += f", {config.et_al_text}"

        return result

    def _format_single_author(self, author: str, config: AuthorFormatConfig) -> str:
        """단일 저자 포맷팅.

        Args:
            author: 저자 이름 (다양한 형식 지원)
            config: 저자 포맷 설정

        Returns:
            포맷된 저자 이름

        Supported formats:
            - "Park SM" (이미 포맷됨)
            - "S-M. Park" (이니셜 + 성)
            - "Sang-Min Park" (이름 + 성)
            - "Park, Sang-Min" (성, 이름)
        """
        # 빈 문자열 처리
        if not author or not author.strip():
            return ""

        author = author.strip()

        # 이미 "Park SM" 또는 "Van Der Park SM" 형식인 경우
        # 마지막에 대문자 이니셜이 있는 패턴
        if re.match(r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s+[A-Z][A-Z-]*$', author):
            return author

        # "S-M. Park" 또는 "Sang-Min Park" 형식 파싱
        parts = author.replace(".", "").split()
        if not parts:
            return author

        # 빈 파트 제거
        parts = [p for p in parts if p.strip()]
        if not parts:
            return author

        # 마지막이 성(Last name)으로 가정
        if len(parts) == 1:
            return parts[0]

        last_name = parts[-1]
        first_parts = parts[:-1]

        # 이니셜 추출
        initials = ""
        for part in first_parts:
            if not part:  # 빈 파트 스킵
                continue
            if "-" in part and config.hyphen_handling == "keep":
                # "Sang-Min" -> "S-M"
                sub_parts = [p for p in part.split("-") if p]
                if sub_parts:
                    initials += "-".join(p[0].upper() for p in sub_parts)
            else:
                # "Sang" -> "S"
                initials += part[0].upper()

        # 이니셜 포맷
        if config.initials_format == "dots":
            # "S-M" -> "S.-M." 형식으로 변환 (APA 스타일)
            if "-" in initials:
                parts = initials.split("-")
                initials = ".-".join(parts) + "."
            else:
                initials = ".".join(initials) + "."
        elif config.initials_format == "space":
            if "-" in initials:
                initials = initials.replace("-", " ")
            else:
                initials = " ".join(initials)

        if config.format == "last_initials":
            return f"{last_name} {initials}"
        elif config.format == "last_first":
            return f"{last_name}, {' '.join(first_parts)}"
        else:
            return author

    def _format_title(self, title: str, config: StyleConfig) -> str:
        """제목 포맷팅.

        Args:
            title: 논문 제목
            config: 스타일 설정

        Returns:
            포맷된 제목
        """
        if not title or not title.strip():
            return ""

        title = title.strip()

        # 대소문자 처리
        if config.title_case == "sentence":
            # 첫 글자만 대문자 (약어 제외)
            if len(title) > 1:
                title = title[0].upper() + title[1:]
            else:
                title = title.upper()
        elif config.title_case == "title":
            title = title.title()

        # 인용부호
        if config.title_quotes:
            title = f'"{title}"'

        # 이탤릭
        if config.title_italics:
            title = f"*{title}*"

        return title

    def _format_publication_info(self, paper: PaperReference, config: StyleConfig) -> str:
        """출판 정보 포맷팅 (연도, 볼륨, 이슈, 페이지).

        Args:
            paper: 논문 정보
            config: 스타일 설정

        Returns:
            포맷된 출판 정보 문자열
        """
        parts = []

        # 연도
        if paper.year:
            year_str = str(paper.year)
            if config.date.format == "year_month" and paper.month:
                months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
                if 1 <= paper.month <= 12:
                    year_str = f"{paper.year} {months[paper.month]}"
            parts.append(year_str)

        # 볼륨/이슈
        if paper.volume:
            try:
                vol_str = config.volume_format.format(
                    volume=paper.volume,
                    issue=paper.issue or ""
                )
            except KeyError:
                # 잘못된 format string일 경우 기본 형식 사용
                vol_str = f"{paper.volume}"
                if paper.issue:
                    vol_str += f"({paper.issue})"

            # 이슈가 없으면 빈 괄호 제거
            vol_str = vol_str.replace("()", "")

            if config.volume_bold:
                vol_str = f"**{vol_str}**"

            parts.append(vol_str)

        # 페이지
        if paper.pages:
            pages = paper.pages
            if config.pages_format == "abbreviated":
                pages = self._abbreviate_pages(pages)

            if parts:
                parts[-1] += f"{config.pages_prefix}{pages}"
            else:
                parts.append(pages)

        return ";".join(parts) if parts else ""

    def _abbreviate_pages(self, pages: str) -> str:
        """페이지 약어화 (123-130 -> 123-30).

        Args:
            pages: 페이지 범위 문자열

        Returns:
            약어화된 페이지 범위

        Supported formats:
            - "123-130" -> "123-30"
            - "e123-e145" -> "e123-e145" (electronic pages 유지)
            - "S1-S10" -> "S1-S10" (supplement pages 유지)
            - "1-3, 5-7" -> "1-3, 5-7" (복수 범위 유지)
        """
        if not pages or not pages.strip():
            return pages

        pages = pages.strip()

        # 특수 페이지 형식은 그대로 반환 (e-pages, supplement, 복수 범위)
        if re.search(r'[eES]|,', pages):
            return pages

        # 숫자만 있는 페이지 범위 처리
        match = re.match(r'^(\d+)-(\d+)$', pages)
        if not match:
            return pages

        start, end = match.groups()
        if len(start) == len(end) and len(start) > 2:
            # 앞자리가 같으면 생략
            common_prefix = 0
            for i, (s, e) in enumerate(zip(start, end)):
                if s == e:
                    common_prefix = i + 1
                else:
                    break

            if common_prefix > 0 and common_prefix < len(end):
                return f"{start}-{end[common_prefix:]}"

        return pages

    def format_multiple(
        self,
        papers: List[PaperReference],
        style: Optional[str] = None,
        journal: Optional[str] = None,
        numbered: bool = True,
        start_number: int = 1,
    ) -> str:
        """여러 논문 포맷팅.

        Args:
            papers: 논문 목록
            style: 스타일명
            journal: 저널명
            numbered: 번호 붙이기 여부
            start_number: 시작 번호

        Returns:
            포맷된 참고문헌 목록
        """
        results = []
        for i, paper in enumerate(papers):
            ref = self.format(paper, style=style, journal=journal)
            if numbered:
                results.append(f"{start_number + i}. {ref}")
            else:
                results.append(ref)

        return "\n".join(results)

    def to_bibtex(self, paper: PaperReference) -> str:
        """BibTeX 형식으로 변환."""
        # Citation key 생성: 첫 번째 저자의 성 + 연도
        # "Park SM" -> "Park", "Kim JH" -> "Kim"
        first_author = "Unknown"
        if paper.authors:
            author_parts = paper.authors[0].split()
            if author_parts:
                # 첫 번째 파트가 성 (Last name)
                first_author = author_parts[0]
        key = f"{first_author}{paper.year or 'nd'}"

        lines = [f"@article{{{key},"]

        if paper.title:
            lines.append(f'  title = {{{paper.title}}},')
        if paper.authors:
            lines.append(f'  author = {{{" and ".join(paper.authors)}}},')
        if paper.journal:
            lines.append(f'  journal = {{{paper.journal}}},')
        if paper.year:
            lines.append(f'  year = {{{paper.year}}},')
        if paper.volume:
            lines.append(f'  volume = {{{paper.volume}}},')
        if paper.issue:
            lines.append(f'  number = {{{paper.issue}}},')
        if paper.pages:
            lines.append(f'  pages = {{{paper.pages}}},')
        if paper.doi:
            lines.append(f'  doi = {{{paper.doi}}},')
        if paper.pmid:
            lines.append(f'  pmid = {{{paper.pmid}}},')

        lines.append("}")
        return "\n".join(lines)

    def to_ris(self, paper: PaperReference) -> str:
        """RIS 형식으로 변환 (EndNote/Zotero 호환)."""
        lines = ["TY  - JOUR"]

        if paper.title:
            lines.append(f"TI  - {paper.title}")
        for author in paper.authors:
            lines.append(f"AU  - {author}")
        if paper.journal:
            lines.append(f"JO  - {paper.journal}")
        if paper.journal_abbrev:
            lines.append(f"JA  - {paper.journal_abbrev}")
        if paper.year:
            lines.append(f"PY  - {paper.year}")
        if paper.volume:
            lines.append(f"VL  - {paper.volume}")
        if paper.issue:
            lines.append(f"IS  - {paper.issue}")
        if paper.pages:
            if "-" in paper.pages:
                sp, ep = paper.pages.split("-", 1)
                lines.append(f"SP  - {sp}")
                lines.append(f"EP  - {ep}")
            else:
                lines.append(f"SP  - {paper.pages}")
        if paper.doi:
            lines.append(f"DO  - {paper.doi}")
        if paper.pmid:
            lines.append(f"AN  - {paper.pmid}")

        lines.append("ER  - ")
        return "\n".join(lines)


# 편의 함수
def format_reference(
    metadata: Dict[str, Any],
    style: str = "vancouver",
    paper_id: str = "",
) -> str:
    """참고문헌 포맷팅 편의 함수."""
    formatter = ReferenceFormatter()
    paper = PaperReference.from_metadata(metadata, paper_id)
    return formatter.format(paper, style=style)
