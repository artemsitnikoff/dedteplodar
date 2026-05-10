"""FAQ API router for YAML file management."""

from pathlib import Path
from fastapi import APIRouter, HTTPException
import yaml

from admin.schemas.pipeline import FAQContent

router = APIRouter(prefix="/faq", tags=["FAQ"])

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
COMPANY_FAQ_PATH = PROJECT_ROOT / "base" / "company_faq.yaml"
DEALERS_PATH = PROJECT_ROOT / "base" / "dealers.yaml"


@router.get("/company")
async def get_company_faq():
    """Get company FAQ YAML content as raw string."""
    try:
        with open(COMPANY_FAQ_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return FAQContent(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Company FAQ file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@router.put("/company")
async def update_company_faq(data: FAQContent):
    """Update company FAQ YAML content."""
    try:
        # Validate YAML syntax
        yaml.safe_load(data.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML syntax: {str(e)}")

    try:
        # Ensure directory exists
        COMPANY_FAQ_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        with open(COMPANY_FAQ_PATH, "w", encoding="utf-8") as f:
            f.write(data.content)

        return {"message": "Company FAQ updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing file: {str(e)}")


@router.get("/dealers")
async def get_dealers():
    """Get dealers YAML content as raw string."""
    try:
        with open(DEALERS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        return FAQContent(content=content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Dealers file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")


@router.put("/dealers")
async def update_dealers(data: FAQContent):
    """Update dealers YAML content."""
    try:
        # Validate YAML syntax
        yaml.safe_load(data.content)
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML syntax: {str(e)}")

    try:
        # Ensure directory exists
        DEALERS_PATH.parent.mkdir(parents=True, exist_ok=True)

        # Write content to file
        with open(DEALERS_PATH, "w", encoding="utf-8") as f:
            f.write(data.content)

        return {"message": "Dealers updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error writing file: {str(e)}")