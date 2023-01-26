function covar = cvarpds(y,pds)
% PURPOSE: This function computes a weighted covariance matrix of y, 
% each row affected by the corresponding weight in pds (pds must be >0 but 
% does not need to be normalized)
%--------------------------------------------------------------
% USAGE: covar = cvarpds(y,pds)
% where:   y =  nx1 vector of the variable
%          pds = nx1 vector of the weights
%--------------------------------------------------------------
% OUTPUTS: covar = covariance matrix of y
%--------------------------------------------------------------
% used in sirmap.m
%------------------------------------------------------------------------
% Yves Aragon, June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


k = find( pds <= 0);
if ~isempty(k) 
'Caution in function cvarpds, the weights are negative'
end
l = sum(pds);
pdsl = pds /l;

%mean
my = sum(diag(pdsl) * y)';
%var-covar
covar =  y' * diag(pdsl) * y  - my*my';
