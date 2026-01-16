"""
FileGenerationTools with S3 storage integration.

Drop-in replacement for agno's FileGenerationTools that supports:
- Local storage (default): Files saved to disk, returns File with content for blob download
- S3 storage: Files uploaded to S3, DB records created, returns downloadable file:xxx ID

Usage in agent definition:
    from src.agentos.tools.file_generation_s3 import FileGenerationTools

    # Local mode (for dev/testing)
    FileGenerationTools(output_directory=config.artifact_output_dir)

    # S3 mode (for production)
    FileGenerationTools(
        output_directory=config.artifact_output_dir,
        storage_mode="s3",
        s3_client=s3_client,
    )
"""

import csv
import io
import json
import asyncio
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, Callable
from uuid import uuid4
from io import BytesIO

from agno.media import File
from agno.tools import Toolkit
from agno.tools.function import ToolResult
from agno.utils.log import logger

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    logger.warning("reportlab not installed. PDF generation will not be available.")


class FileGenerationTools(Toolkit):
    """
    File generation toolkit with configurable storage backend.

    Args:
        storage_mode: "local" or "s3" - where to store generated files
        output_directory: Local directory for file storage
        s3_client: S3Client instance (required for s3 mode)
        enable_*: Enable/disable specific file types
    """

    def __init__(
        self,
        enable_json_generation: bool = True,
        enable_csv_generation: bool = True,
        enable_pdf_generation: bool = True,
        enable_txt_generation: bool = True,
        output_directory: Optional[str] = None,
        storage_mode: str = "local",  # "local" or "s3"
        s3_client: Optional[Any] = None,  # S3Client instance
        all: bool = False,
        **kwargs,
    ):
        self.enable_json_generation = enable_json_generation
        self.enable_csv_generation = enable_csv_generation
        self.enable_pdf_generation = enable_pdf_generation and PDF_AVAILABLE
        self.enable_txt_generation = enable_txt_generation
        self.output_directory = Path(output_directory) if output_directory else None
        self.storage_mode = storage_mode
        self._s3_client = s3_client

        # Validate s3 mode requirements
        if storage_mode == "s3" and s3_client is None:
            logger.warning("S3 mode requested but no s3_client provided. Falling back to local mode.")
            self.storage_mode = "local"

        # Create output directory if specified
        if self.output_directory:
            self.output_directory.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Files will be saved to: {self.output_directory}")

        if enable_pdf_generation and not PDF_AVAILABLE:
            logger.warning("PDF generation requested but reportlab is not installed.")
            self.enable_pdf_generation = False

        tools: List[Any] = []
        if all or enable_json_generation:
            tools.append(self.generate_json_file)
        if all or enable_csv_generation:
            tools.append(self.generate_csv_file)
        if all or (enable_pdf_generation and PDF_AVAILABLE):
            tools.append(self.generate_pdf_file)
        if all or enable_txt_generation:
            tools.append(self.generate_text_file)

        super().__init__(name="file_generation", tools=tools, **kwargs)

    def _save_file_to_disk(self, content: Union[str, bytes], filename: str) -> Optional[Path]:
        """Save file to disk if output_directory is set. Return file path or None."""
        if not self.output_directory:
            return None

        file_path = self.output_directory / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, str):
            file_path.write_text(content, encoding="utf-8")
        else:
            file_path.write_bytes(content)

        logger.debug(f"File saved to: {file_path}")
        return file_path

    def _upload_to_s3_sync(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        dependencies: Optional[Dict[str, Any]] = None
    ) -> Optional[File]:
        """
        Upload file to S3 and create DB records synchronously.
        Returns File with proper file:xxx ID, or None on failure.
        """
        try:
            # Get auth token from dependencies
            token = dependencies.get("_auth_token") if dependencies else None
            if not token:
                logger.warning("No auth token for S3 upload, falling back to local-only")
                return None

            # Run async upload in sync context
            return asyncio.get_event_loop().run_until_complete(
                self._upload_to_s3_async(content, filename, mime_type, token)
            )
        except RuntimeError:
            # No event loop running, create one
            return asyncio.run(
                self._upload_to_s3_async(content, filename, mime_type, token)
            )
        except Exception as e:
            logger.error(f"S3 upload failed: {e}")
            return None

    async def _upload_to_s3_async(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        token: str
    ) -> Optional[File]:
        """
        Async implementation of S3 upload + DB record creation.
        """
        try:
            # Import here to avoid circular imports
            from src.shared.db.repository import repo_create, ensure_record_id, current_user_token

            # Set user token context for RLS
            current_user_token.set(token)

            # Upload to S3
            with BytesIO(content) as f:
                upload_result = self._s3_client.upload_file(
                    f,
                    filename,
                    content_type=mime_type
                )

            # Extract user ID from token for uploader field
            import jwt
            decoded = jwt.decode(token, options={"verify_signature": False})
            user_id = decoded.get("ID")  # e.g., "user:demo_model_test"

            # Create file record in SurrealDB
            file_record = {
                "uploader": ensure_record_id(user_id),
                "s3_bucket": upload_result["bucket"],
                "s3_key": upload_result["key"],
                "hash_sha256": upload_result["hash"],
                "size_bytes": upload_result["size"],
                "mime_type": mime_type,
                "extension": Path(filename).suffix,
                "status": "completed"
            }

            file_result = await repo_create("file", file_record)

            if not file_result or len(file_result) == 0:
                logger.error(f"Failed to create file record for {filename}")
                return None

            file_id = str(file_result[0].get("id"))

            # Create source record for download permission (RLS)
            source_record = {
                "title": f"Generated: {filename}",
                "file_ref": ensure_record_id(file_id),
                "asset": {"file_ref": file_id},
            }

            await repo_create("source", source_record)
            logger.info(f"Created file {file_id} and source record for {filename}")

            return File(
                id=file_id,  # file:xxx format from SurrealDB
                url=f"/api/files/{file_id}/download",
                filename=filename,
                mime_type=mime_type,
                size=len(content),
            )

        except Exception as e:
            logger.error(f"S3 upload/DB creation failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_file_artifact(
        self,
        content: bytes,
        filename: str,
        mime_type: str,
        file_type: str,
        file_path: Optional[Path],
        dependencies: Optional[Dict[str, Any]] = None,
    ) -> File:
        """
        Create File artifact based on storage mode.

        - S3 mode: Upload to S3, create DB records, return file:xxx ID
        - Local mode: Return File with embedded content for blob download
        """
        if self.storage_mode == "s3":
            s3_file = self._upload_to_s3_sync(content, filename, mime_type, dependencies)
            if s3_file:
                return s3_file
            # Fall through to local mode if S3 failed
            logger.warning(f"S3 upload failed for {filename}, returning local file")

        # Local mode: Return file with content embedded
        # Prefix ID with "file:" for format compatibility
        file_id = f"file:{uuid4()}"

        return File(
            id=file_id,
            content=content,
            mime_type=mime_type,
            file_type=file_type,
            filename=filename,
            size=len(content),
            filepath=str(file_path) if file_path else None,
            # For local mode, frontend can use content for blob download
            # url is set to indicate this is a local file
            url=f"blob:{file_id}",
        )

    def generate_json_file(
        self,
        data: Union[Dict, List, str],
        filename: Optional[str] = None,
        dependencies: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Generate a JSON file from the provided data."""
        try:
            logger.debug(f"Generating JSON file with data: {type(data)}")

            # Handle different input types
            if isinstance(data, str):
                try:
                    json.loads(data)
                    json_content = data
                except json.JSONDecodeError:
                    json_content = json.dumps({"content": data}, indent=2)
            else:
                json_content = json.dumps(data, indent=2, ensure_ascii=False)

            # Generate filename if not provided
            if not filename:
                filename = f"generated_file_{str(uuid4())[:8]}.json"
            elif not filename.endswith(".json"):
                filename += ".json"

            # Save to disk
            file_path = self._save_file_to_disk(json_content, filename)
            content_bytes = json_content.encode("utf-8")

            # Create file artifact (S3 or local based on storage_mode)
            file_artifact = self._create_file_artifact(
                content=content_bytes,
                filename=Path(filename).name,
                mime_type="application/json",
                file_type="json",
                file_path=file_path,
                dependencies=dependencies,
            )

            success_msg = f"JSON file '{filename}' generated ({len(json_content)} chars)."
            if self.storage_mode == "s3" and file_artifact.id.startswith("file:"):
                success_msg += f" Available for download."
            elif file_path:
                success_msg += f" Saved to: {file_path}"

            return ToolResult(content=success_msg, files=[file_artifact])

        except Exception as e:
            logger.error(f"Failed to generate JSON file: {e}")
            return ToolResult(content=f"Error generating JSON file: {e}")

    def generate_csv_file(
        self,
        data: Union[List[List], List[Dict], str],
        filename: Optional[str] = None,
        headers: Optional[List[str]] = None,
        dependencies: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Generate a CSV file from the provided data."""
        try:
            logger.debug(f"Generating CSV file with data: {type(data)}")

            output = io.StringIO()

            if isinstance(data, str):
                csv_content = data
            elif isinstance(data, list) and len(data) > 0:
                writer = csv.writer(output)

                if isinstance(data[0], dict):
                    if data:
                        fieldnames = list(data[0].keys())
                        writer.writerow(fieldnames)
                        for row in data:
                            if isinstance(row, dict):
                                writer.writerow([row.get(field, "") for field in fieldnames])
                            else:
                                writer.writerow([str(row)] + [""] * (len(fieldnames) - 1))
                elif isinstance(data[0], list):
                    if headers:
                        writer.writerow(headers)
                    writer.writerows(data)
                else:
                    if headers:
                        writer.writerow(headers)
                    for item in data:
                        writer.writerow([str(item)])

                csv_content = output.getvalue()
            else:
                csv_content = ""

            if not filename:
                filename = f"generated_file_{str(uuid4())[:8]}.csv"
            elif not filename.endswith(".csv"):
                filename += ".csv"

            file_path = self._save_file_to_disk(csv_content, filename)
            content_bytes = csv_content.encode("utf-8")

            file_artifact = self._create_file_artifact(
                content=content_bytes,
                filename=filename,
                mime_type="text/csv",
                file_type="csv",
                file_path=file_path,
                dependencies=dependencies,
            )

            success_msg = f"CSV file '{filename}' generated ({len(csv_content)} chars)."
            if self.storage_mode == "s3" and file_artifact.id.startswith("file:"):
                success_msg += f" Available for download."
            elif file_path:
                success_msg += f" Saved to: {file_path}"

            return ToolResult(content=success_msg, files=[file_artifact])

        except Exception as e:
            logger.error(f"Failed to generate CSV file: {e}")
            return ToolResult(content=f"Error generating CSV file: {e}")

    def generate_pdf_file(
        self,
        content: str,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        dependencies: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Generate a PDF file from the provided content."""
        if not PDF_AVAILABLE:
            return ToolResult(
                content="PDF generation not available. Install reportlab: pip install reportlab"
            )

        try:
            logger.debug(f"Generating PDF file with content length: {len(content)}")

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=1 * inch)

            styles = getSampleStyleSheet()
            title_style = styles["Title"]
            normal_style = styles["Normal"]

            story = []

            if title:
                story.append(Paragraph(title, title_style))
                story.append(Spacer(1, 20))

            paragraphs = content.split("\n\n")
            for para in paragraphs:
                if para.strip():
                    clean_para = para.strip().replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(clean_para, normal_style))
                    story.append(Spacer(1, 10))

            doc.build(story)
            pdf_content = buffer.getvalue()
            buffer.close()

            if not filename:
                filename = f"generated_file_{str(uuid4())[:8]}.pdf"
            elif not filename.endswith(".pdf"):
                filename += ".pdf"

            file_path = self._save_file_to_disk(pdf_content, filename)

            file_artifact = self._create_file_artifact(
                content=pdf_content,
                filename=Path(filename).name,
                mime_type="application/pdf",
                file_type="pdf",
                file_path=file_path,
                dependencies=dependencies,
            )

            success_msg = f"PDF file '{filename}' generated ({len(pdf_content)} bytes)."
            if self.storage_mode == "s3" and file_artifact.id.startswith("file:"):
                success_msg += f" Available for download."
            elif file_path:
                success_msg += f" Saved to: {file_path}"

            return ToolResult(content=success_msg, files=[file_artifact])

        except Exception as e:
            logger.error(f"Failed to generate PDF file: {e}")
            return ToolResult(content=f"Error generating PDF file: {e}")

    def generate_text_file(
        self,
        content: str,
        filename: Optional[str] = None,
        dependencies: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Generate a text file from the provided content."""
        try:
            logger.debug(f"Generating text file with content length: {len(content)}")

            if not filename:
                filename = f"generated_file_{str(uuid4())[:8]}.txt"
            elif not Path(filename).suffix:
                filename += ".txt"

            def _get_file_info(filename: str) -> tuple:
                """Return (mime_type, file_type) based on filename extension.

                Note: MIME types must be in agno's valid_mime_types() list.
                See: agno/media.py File.valid_mime_types()
                """
                extension_map = {
                    '.py': ('text/x-python', 'py'),
                    '.md': ('text/md', 'md'),  # agno uses 'text/md' not 'text/markdown'
                    '.txt': ('text/plain', 'txt'),
                    '.json': ('application/json', 'json'),
                    '.csv': ('text/csv', 'csv'),
                    '.xml': ('text/xml', 'xml'),
                    '.html': ('text/html', 'html'),
                    '.css': ('text/css', 'css'),
                    '.js': ('text/javascript', 'js'),
                    '.yaml': ('text/plain', 'yaml'),  # text/yaml not in agno valid list
                    '.yml': ('text/plain', 'yml'),
                    '.toml': ('text/plain', 'toml'),
                    '.sh': ('text/plain', 'sh'),  # text/x-shellscript not in agno valid list
                    '.sql': ('text/plain', 'sql'),  # text/x-sql not in agno valid list
                    '.rst': ('text/plain', 'rst'),  # text/x-rst not in agno valid list
                }
                suffix = Path(filename).suffix.lower()
                return extension_map.get(suffix, ('text/plain', 'txt'))

            mime_type, file_type = _get_file_info(filename)
            file_path = self._save_file_to_disk(content, filename)
            content_bytes = content.encode("utf-8")

            file_artifact = self._create_file_artifact(
                content=content_bytes,
                filename=Path(filename).name,
                mime_type=mime_type,
                file_type=file_type,
                file_path=file_path,
                dependencies=dependencies,
            )

            success_msg = f"Text file '{filename}' generated ({len(content)} chars)."
            if self.storage_mode == "s3" and file_artifact.id.startswith("file:"):
                success_msg += f" Available for download."
            elif file_path:
                success_msg += f" Saved to: {file_path}"

            return ToolResult(content=success_msg, files=[file_artifact])

        except Exception as e:
            logger.error(f"Failed to generate text file: {e}")
            return ToolResult(content=f"Error generating text file: {e}")
