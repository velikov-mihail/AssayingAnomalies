function [inertia,casecoord,varcoord]=genpca(data,varargin)
% PURPOSE : Generalized pca implementation
%---------------------------------------------------------------------------
% USAGE : [inertia,casecoord,varcoord]=genpca(data,weight,metric,center,reduc)
%    where : data : (n x p) data matrix
%            weight : optional (n x 1) weight vector. The default is weight=(1/n,...,1/n)'.
%            metric : optional (p x p) matrix. The default is the identity matrix.
%            center : optional boolean: if center=1 : the pca is centered (default).
%                                       if center=0 : the pca is not centered.
%            reduc : optional boolean: if reduc=1 : the pca is standardized (default).
%                                      if reduc=0 : the pca is not standardized.
%----------------------------------------------------------------------------- 
% OUTPUTS :  Inertia : (p x 1) vector of inertia
%            casecoord : (n x p) matrix containing the case coordinates (principal components)
%            varcoord : (p x p) matrix containing the variables coordinates
%-----------------------------------------------------------------------------   
% used in pcamap.m
%------------------------------------------------------------------------
% Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


x=data;
w=ones(size(data,1),1)/size(data,1);
m=eye(size(data,2));
center=1;
reduc=1;
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        w=varargin{1};
    end;
    if t>=2 & ~isempty(varargin{2})
        m=varargin{2};
    end;
    if t>=3 & ~isempty(varargin{3})
        center=varargin{3};
    end;
    if t==4 & ~isempty(varargin{4})
        reduc=varargin{4};
    end;
end;

w=w/sum(w);
W=diag(w);
xbar=sum(repmat(w,1,size(data,2)).*data)';

if center==1
    xc=x-ones(size(x,1),1)*xbar';
else
    xc=x;
end;

sig2=sum(repmat(w,1,size(x,2)).*(x.^2))'-xbar.^2;
sigma=(size(x,1)/(size(x,1)-1))*diag(sig2);
sigmademi=sqrt(((size(x,1)-1)/size(x,1)))*diag(sig2.^(-1/2));

if reduc==1
    xcr=xc*sigmademi;
else
    xcr=xc;
end;

cov=xcr'*W*xcr;
l=chol(m);
covn=l*cov*l';
[U,D]=eigs(covn);
V=l'*U;
casecoord=xcr*V;
Dv=diag(D);
Dvdemi=Dv.^(-1/2);
Ddemi=diag(Dvdemi);
varcoord=cov*V*Ddemi;
inertia=Dv;