function [out,inertia,casecoord,varcoord]=pcamap(long,lat,data,varargin)
% PURPOSE: This function links a map and a pca plot
%------------------------------------------------------------------------
% USAGE: [out,inertia,casecoord,varcoord]=pcamap(long,lat,data,direct,weight,metric,center,reduc,carte,label,symbol)
%   where : 
%           long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%           data = n x 1 vector of the variable to study on the first axis
%           direct = 1 x 2 vector of the principal component number to be plotted on the 2 axis
%           weight : optional (n x 1) weight vector. The default is weight=(1/n,...,1/n)'.
%           metric : optional (p x p) matrix. The default is the identity matrix.
%           center : optional boolean: if center=1 : the pca is centered (default).
%                                      if center=0 : the pca is not centered.
%           reduc : optional boolean: if reduc=1 : the pca is standardized (default).
%                                     if reduc=0 : the pca is not standardized.
%           carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%           label = n x 1 optionnal variable used to label selected observations
%           symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                    * symbol=0 : selected spatial units are marked with a different color only (default)
%------------------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%------------------------------------------------------------------------
% MANUAL: Select points on either the map or the pca plot by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses genpca.m
% -----------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr


close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
x=data;
w=ones(size(data,1),1)/size(data,1);
m=eye(size(data,2));
center=1;
reduc=1;
direct=[1 2];
vectx=[];
vecty=[];




%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save pcafich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%



% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        direct=varargin{1};
    end;
    if t>=2 & ~isempty(varargin{2})
        w=varargin{2};
    end;
    if t>=3 & ~isempty(varargin{3})
        m=varargin{3};
    end;
    if t>=4 & ~isempty(varargin{4})
        center=varargin{4};
    end;
    if t>=5 & ~isempty(varargin{5})
        reduc=varargin{5};
    end;
    if t>=6 & ~isempty(varargin{6})
        carte=varargin{6};
        c=1;
    end;
    if t>=7 & ~isempty(varargin{7})
        label=varargin{7};
        l=1;
    end;
    if t==8 & ~isempty(varargin{8})
        symbol=varargin{8};
    end;
end;

%%%%%%%%%%%%%%%%%%%%%


% compute the pca
[inertia,casecoord,varcoord]=genpca(x,w,m,center,reduc);
inerpart=inertia/sum(inertia);
inerpartperc=inerpart*100;
casequal=casecoord(:,direct(1)).^2+casecoord(:,direct(2)).^2;
den=sum((casecoord'.*casecoord'))';
casequal=sqrt(casequal./den);
casequalperc=casequal*100; % in percent
varqual=varcoord(:,direct(1)).^2+varcoord(:,direct(2)).^2;
denv=sum((varcoord'.*varcoord'))';
varqual=sqrt(varqual./denv);
varqualperc=varqual*100;
%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
%%%%%%%%%%%%%%%%%%%%%

% Trace the pca scatter plots

Axis2=subplot(1,2,2);
plot(casecoord(:,direct(1)),casecoord(:,direct(2)),'b.');
title('Cases scatter plot');
xlabel({['Axis ',num2str(direct(1))];['Inertia part: ',num2str(inerpartperc(direct(1)))]});
ylabel({['Axis ',num2str(direct(2))];['Inertia part: ',num2str(inerpartperc(direct(2)))]});
line([0 0],[max(casecoord(:,direct(2))) min(casecoord(:,direct(2)))],'Color','black');
line([max(casecoord(:,direct(1))) min(casecoord(:,direct(1)))],[0 0],'Color','black');
axis manual;
subplot(Axis1);
axis manual;
Xlim2=get(Axis2,'XLim');
Ylim2=get(Axis2,'YLim');


figure(2);
set(figure(2),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(2),'Units','Pixel');
plot(varcoord(:,direct(1)),varcoord(:,direct(2)),'b.');
title('Variables scatter plot');
xlabel({['Axis ',num2str(direct(1))];['Inertia part: ',num2str(inerpartperc(direct(1)))]});
ylabel({['Axis ',num2str(direct(2))];['Inertia part: ',num2str(inerpartperc(direct(2)))]});
XL=zeros(2,size(varcoord,1));
XL(2,:)=varcoord(:,direct(1))';
YL=zeros(2,size(varcoord,1));
YL(2,:)=varcoord(:,direct(2))';
line([0 0],[max(varcoord(:,direct(2))) min(varcoord(:,direct(2)))],'Color','black');
line([max(varcoord(:,direct(1))) min(varcoord(:,direct(1)))],[0 0],'Color','black');
line(XL,YL,'Color','blue');
vartext=[repmat(' ',length(varqual),1),repmat('var',length(varqual),1),num2str([1:length(varqual)]'),repmat(':',length(varqual),1)];
Htex=text(varcoord(:,direct(1)),varcoord(:,direct(2)),[ vartext,repmat(' ',length(varqual),1) num2str(varqualperc),repmat(' %',length(varqual),1)]);
set(Htex,'FontSize',8);
axis manual;
%%%%%%%%%%%%%%%%%%%%%

% Main loop
figure(1);
maptest=0;
scattertest=0;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    line([0 0],[max(casecoord(:,direct(2))) min(casecoord(:,direct(2)))],'Color','black');
    line([max(casecoord(:,direct(1))) min(casecoord(:,direct(1)))],[0 0],'Color','black');
    if ~isempty(Iunselect)
      plot(casecoord(Iunselect,direct(1)),casecoord(Iunselect,direct(2)),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(casecoord(Iselect,direct(1)),casecoord(Iselect,direct(2)),'b*');
            else
                plot(casecoord(Iselect,direct(1)),casecoord(Iselect,direct(2)),'r.');
            end;
            Htex=text(casecoord(Iselect,direct(1)),casecoord(Iselect,direct(2)),[ repmat(' ',length(casequal(Iselect)),1) num2str(casequalperc(Iselect)),repmat(' %',length(casequal(Iselect)),1)]);
            set(Htex,'FontSize',8);
        elseif scattertest==1
            if symbol==1
                plot(casecoord(Iselect,direct(1)),casecoord(Iselect,direct(2)),'bo');
            else
                plot(casecoord(Iselect,direct(1)),casecoord(Iselect,direct(2)),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
            Htex=text(casecoord(Iselect,direct(1)),casecoord(Iselect,direct(2)),[ repmat(' ',length(casequal(Iselect)),1) num2str(casequalperc(Iselect)),repmat(' %',length(casequal(Iselect)),1)]);
            set(Htex,'FontSize',8);     
        end;
    end;   
    hold off;
    subplot(Axis1);
    hold on;
    cla;
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'b*');
            else
                plot(long(Iselect),lat(Iselect),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif scattertest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'bo');
            else
                plot(long(Iselect),lat(Iselect),'m.');
            end;           
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
   
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            scattertest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % scatterplot selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if scattertest==0
            scattertest=1;
            maptest=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2
            obs=selectstat('scatter',obs,casecoord(:,direct(1)),'point',casecoord(:,direct(2)),x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectstat('scatter',obs,casecoord(:,direct(1)),'poly',casecoord(:,direct(2)),x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%