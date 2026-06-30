"""
Company Logic Module
Handles company business logic and validation.
"""

from typing import Dict, Any, List, Optional


class CompanyLogic:
    """Business logic for company operations."""

    def __init__(self, db):
        """Initialize company logic with database instance."""
        self.db = db

    def get_all_companies(self, visibility: str | None = None) -> Dict[str, Any]:
        """
        Get companies for one visibility pool or the full registry.

        Returns:
            Dict with success status, message, and data
        """
        try:
            companies = self.db.get_all_companies(visibility=visibility)
            return {
                "success": True,
                "message": "Companies retrieved successfully",
                "data": companies
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve companies: {str(e)}",
                "data": []
            }

    def get_active_company(self) -> Dict[str, Any]:
        """
        Get the currently active company.
        
        Returns:
            Dict with success status, message, and data
        """
        try:
            company = self.db.get_active_company()
            if company:
                return {
                    "success": True,
                    "message": "Active company retrieved successfully",
                    "data": company
                }
            else:
                return {
                    "success": False,
                    "message": "No active company",
                    "data": None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to retrieve active company: {str(e)}",
                "data": None
            }

    def validate_company_data(self, company_data: Dict[str, Any],
                            current_company_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Validate company data.
        
        Returns:
            Dict with success status and message
        """
        # Check required fields
        if not company_data.get('business_name', '').strip():
            return {
                "success": False,
                "message": "Business Name is required"
            }

        # Check for duplicate company name
        business_name = company_data['business_name'].strip()
        if current_company_id:
            exists = self.db.company_name_exists_excluding_id(business_name, current_company_id)
        else:
            exists = self.db.company_name_exists(business_name)
        
        if exists:
            return {
                "success": False,
                "message": f"A company with the name '{business_name}' already exists"
            }

        return {
            "success": True,
            "message": "Company data is valid"
        }

    def normalize_company_data(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize company data (ensure proper types and defaults).
        
        Returns:
            Normalized company data dict
        """
        normalized = company_data.copy()

        # Ensure text fields are stripped
        text_fields = ['business_name', 'phone_number', 'gstin', 'gst_type', 'email', 'business_type',
                      'business_category', 'address', 'state', 'pincode', 'financial_year']
        for field in text_fields:
            if field in normalized and normalized[field]:
                normalized[field] = normalized[field].strip()

        # Ensure GSTIN is uppercase
        if normalized.get('gstin'):
            normalized['gstin'] = normalized['gstin'].upper()

        if normalized.get('gst_type') not in ('Regular', 'Composition'):
            normalized['gst_type'] = 'Regular'

        return normalized

    def create_company(self, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new company.
        
        Returns:
            Dict with success status and message
        """
        try:
            # Normalize data
            normalized_data = self.normalize_company_data(company_data)
            if "visibility" not in normalized_data:
                normalized_data["visibility"] = "normal"
            
            # Create company
            success = self.db.create_company(normalized_data)
            
            if success:
                return {
                    "success": True,
                    "message": "Company created successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to create company"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to create company: {str(e)}"
            }

    def update_company(self, company_id: int, company_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update an existing company.
        
        Returns:
            Dict with success status and message
        """
        try:
            # Normalize data
            normalized_data = self.normalize_company_data(company_data)

            validation = self.validate_company_data(
                normalized_data,
                current_company_id=company_id,
            )
            if not validation['success']:
                return validation

            # Update company
            success = self.db.update_company(company_id, normalized_data)
            
            if success:
                return {
                    "success": True,
                    "message": "Company updated successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to update company"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to update company: {str(e)}"
            }

    def set_active_company(self, company_id: int) -> Dict[str, Any]:
        """
        Set a company as active.
        
        Returns:
            Dict with success status and message
        """
        try:
            success = self.db.set_active_company(company_id)
            
            if success:
                return {
                    "success": True,
                    "message": "Active company set successfully"
                }
            else:
                return {
                    "success": False,
                    "message": "Failed to set active company"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to set active company: {str(e)}"
            }

    def delete_company(self, company_id: int) -> Dict[str, Any]:
        """
        Delete a company.
        
        Returns:
            Dict with success status and message
        """
        try:
            success = self.db.delete_company(company_id)
            
            if success:
                return {
                    "success": True,
                    "message": "Company deleted successfully"
                }
            else:
                db_error = getattr(self.db, "last_error_message", None)
                message = "Failed to delete company"
                if db_error:
                    message = f"{message}: {db_error}"
                return {
                    "success": False,
                    "message": message
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to delete company: {str(e)}"
            }
