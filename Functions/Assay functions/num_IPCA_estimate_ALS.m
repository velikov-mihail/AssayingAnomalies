function [ Gamma_New , F_New ] = num_IPCA_estimate_ALS( Gamma_Old , W , X , Nts , varargin )
% [ Gamma_New , F_New ] = num_IPCA_estimate_ALS( Gamma_Old , W , X , Nts )
% [ Gamma_New , F_New ] = num_IPCA_estimate_ALS( Gamma_Old , W , X , Nts , PSF )
% inputs
% - Gamma_Old : LxK matrix of previous iteration's GammaBeta estimate
% - W : LxLxT array of Z(:,:,t)'*Z(:,:,t)/Nts(t)
% - X : LxT array of Z(:,:,t)'*Y(:,t)/Nts(t)
% - Nts : 1xT vector of cross-sectional size [typically found as sum(LOC)]
% - (optional) PSF : Kadd x T Pre-Specified Factors
%
% outputs
% - Gamma_New : LxK matrix of this iteration's GammaBeta estimate
% - F_New : KxT matrix of this iteration's Factor estimate
%
% Imposes identification assumption on Gamma_New and F_New: Gamma_New is orthonormal
% matrix and F_New has positive mean (taken across the T columns)
%
% When nargin>4, estimates a LxKtilde Gamma_New and a Ktilde x T F_New, where
% Ktilde=K+Kadd
% The first K columns of Gamma_New is GammaBeta.
% The last Kadd columns of Gamma_New is GammaDelta.
% We continue to only return the KxT factor estimate in F_New
%
% When nargin<=4, Ktilde=K and GammaDelta is not estimated

if nargin>4 & ~isempty(varargin{1})
    PSF = varargin{1};
    PSF_version = true;
    [Kadd,Tadd] = size(PSF);
else
    PSF_version = false;
end

T = length(Nts);
if PSF_version % pre-specified factors in the model
    [L,Ktilde] = size(Gamma_Old);
    K = Ktilde-Kadd;
else % no pre-specified factors in the model
    [L,K] = size(Gamma_Old);
    Ktilde = K;
end

F_New = [];
if K>0 % this could run using only prespecified factors
    
if PSF_version % pre-specified factors in the model
    F_New = nan(K,T);
    for t=1:T
        F_New(:,t) = ( Gamma_Old(:,1:K)'*W(:,:,t)*Gamma_Old(:,1:K) )\...
            ( Gamma_Old(:,1:K)'*( X(:,t)-W(:,:,t)*Gamma_Old(:,K+1:Ktilde)*PSF(:,t) ) );
    end
else % no pre-specified factors in the model
    F_New = nan(K,T);
    for t=1:T
        F_New(:,t) = ( Gamma_Old'*W(:,:,t)*Gamma_Old )\( Gamma_Old'*X(:,t) ); % Equation (6)
    end
end

end


Numer = zeros(L*Ktilde,1);
Denom = zeros(L*Ktilde);
if PSF_version % pre-specified factors in the model
    if K>0
        for t=1:T
            Numer = Numer + kron( X(:,t)        , [F_New(:,t);PSF(:,t)]                            )*Nts(t);
            Denom = Denom + kron( W(:,:,t)      , [F_New(:,t);PSF(:,t)]*[F_New(:,t);PSF(:,t)]'     )*Nts(t);
        end
    else
        for t=1:T
            Numer = Numer + kron( X(:,t)        , [PSF(:,t)]                            )*Nts(t);
            Denom = Denom + kron( W(:,:,t)      , [PSF(:,t)]*[PSF(:,t)]'     )*Nts(t);
        end
    end
else % no pre-specified factors in the model
    for t=1:T % Equation (7)
        Numer = Numer + kron( X(:,t)        , F_New(:,t)                )*Nts(t);
        Denom = Denom + kron( W(:,:,t)      , F_New(:,t)*F_New(:,t)'    )*Nts(t);
    end
end
Gamma_New_trans_vec = Denom\Numer;
Gamma_New_trans     = reshape(Gamma_New_trans_vec,Ktilde,L);
Gamma_New           = Gamma_New_trans';

% GammaBeta orthonormal and F_New Orthogonal
if K>0
R1                  = chol(Gamma_New(:,1:K)'*Gamma_New(:,1:K),'upper');
[R2,~,~]            = svd(R1*F_New*F_New'*R1');
Gamma_New(:,1:K)    = (Gamma_New(:,1:K)/R1)*R2;
F_New               = R2\(R1*F_New);
end

% Sign convention on GammaBeta and F_New
if K>0
sg = sign(mean(F_New,2));
sg(sg==0)=1; % if mean zero, do not flip signs of anything
Gamma_New(:,1:K) = Gamma_New(:,1:K).*sg';
F_New = F_New .* sg;
end

% Orthogonality between GammaBeta and GammaDelta/Alpha (generically call Gammadelta)
if PSF_version & K>0
    Gammabeta = Gamma_New(:,1:K);
    Gammadelta = Gamma_New(:,K+1:end);
    Gammadelta = ( eye(L) - Gammabeta*Gammabeta' )*Gammadelta;
  
    gamma = Gammabeta'*Gammadelta; %K x Kadd reg coef
    F_New = F_New + gamma*PSF;

    Gamma_New = [Gammabeta Gammadelta];
    
    % AGAIN: Sign convention on GammaBeta and F_New
    sg = sign(mean(F_New,2));
    sg(sg==0)=1; % if mean zero, do not flip signs of anything
    Gamma_New(:,1:K) = Gamma_New(:,1:K).*sg';
    F_New = F_New .* sg;
end



end

